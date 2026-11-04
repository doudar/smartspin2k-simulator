"""Short, paired high-power diagnostics; archived long-ride policy is unchanged.

Uses the exact published early prefix and CPS/CSC ingress, not Peloton cable
windows. Both effective plant and delivered sensor power are scored separately.
"""
import argparse
from dataclasses import asdict
import hashlib
import json
import math
from pathlib import Path

import numpy as np

from . import baseline
from .adapter import file_fingerprint, load_adapter, source_provenance
from .cli import PACKAGE
from .longride import coverage, digest, probe, run_one
from .model import BikeConfig
from .performance import DEFAULT_BUDGET, RELATIVE_ALLOWANCE, compare
from .workout import Segment, Workout

EXPERIMENT = 'high-power-early-prefix-v1'
DWELL_S = 5.
GOAL_S = 10.
SPRINT_START_S = 390.
RECOVERY_START_S = 415.
DURATION_S = 445.


def diagnostic_workout(target_w):
    """Preserve every published segment/cadence before changing only sprint watts."""
    if not math.isfinite(target_w) or not 240 < target_w <= 1000:
        raise ValueError('Diagnostic sprint target must be >240 and <=1000 W')
    return Workout([*probe(), Segment(30,100,100,85),
                    Segment(25,target_w,target_w,85), Segment(30,100,100,85)])


def _band_response(times, power, dt, target_w, start_s, band_w, dwell_s):
    inside = np.abs(power-target_w) <= band_w
    first = np.flatnonzero(inside)
    run_start = None
    dwell_start = dwell_confirmed = None
    for i, ok in enumerate(inside):
        if not ok:
            run_start = None
        elif run_start is None:
            run_start = float(times[i])
        if ok and times[i]+dt[i]-run_start >= dwell_s-1e-9 and dwell_start is None:
            dwell_start = run_start
            dwell_confirmed = run_start+dwell_s
    end_s = float(times[-1]+dt[-1])
    final = run_start if run_start is not None and end_s-run_start >= dwell_s-1e-9 else None
    later_dt = np.maximum(0., times+dt-np.maximum(times, dwell_confirmed)) if dwell_confirmed is not None else np.zeros(len(times))
    later_outside = (~inside) & (later_dt > 0)
    excursion_starts = later_outside & ~np.r_[False,later_outside[:-1]]
    return {'band_w':band_w,'dwell_s':dwell_s,
            'first_entry_s':float(times[first[0]]-start_s) if len(first) else None,
            'first_dwell_entry_s':dwell_start-start_s if dwell_start is not None else None,
            'first_dwell_confirmed_s':dwell_confirmed-start_s if dwell_confirmed is not None else None,
            'final_settling_s':final-start_s if final is not None else None,
            'outside_band_s':float(dt[~inside].sum()),
            'above_band_s':float(dt[power>target_w+band_w].sum()),
            'below_band_s':float(dt[power<target_w-band_w].sum()),
            'later_excursion_count':int(excursion_starts.sum()) if dwell_confirmed is not None else None,
            'later_excursion_s':float(later_dt[later_outside].sum()) if dwell_confirmed is not None else None,
            'later_max_absolute_error_w':float(np.max(np.abs(power[later_outside]-target_w))) if later_outside.any() else (0. if dwell_confirmed is not None else None)}


def phase_response(trace, target_w, start_s, end_s, *, column=2, dwell_s=DWELL_S):
    """Dwell starts at entry; confirmation is five seconds later.

    Final settling is the last in-band run through phase end, requiring the same
    predeclared dwell. Null means no qualifying run. Sample values are held to
    the next tick, clipped at phase end, matching existing scoring semantics.
    Later excursions begin after first-dwell confirmation, never hidden by it.
    """
    data = np.asarray(trace,dtype=float)
    if not all(math.isfinite(x) for x in (target_w,start_s,end_s,dwell_s)) or end_s<=start_s or dwell_s<=0:
        raise ValueError('Need a finite positive phase duration and dwell')
    if data.ndim!=2 or column<0 or data.shape[1]<=max(0,column) or not len(data):
        raise ValueError('Need a nonempty trace with the requested power column')
    if not np.isfinite(data[:,[0,column]]).all() or np.any(np.diff(data[:,0])<=0):
        raise ValueError('Need finite power and strictly increasing timestamps')
    part=data[(data[:,0]>=start_s)&(data[:,0]<end_s)]
    if not len(part) or not math.isclose(float(part[0,0]),start_s,abs_tol=1e-9):
        raise ValueError('Trace must include the phase start')
    times,power=part[:,0],part[:,column]
    dt=np.diff(np.r_[times,end_s])
    if np.any(dt<=0) or np.max(dt)>1.01:
        raise ValueError('Phase must have no independent-clock gaps over one second')
    reached=np.flatnonzero(power>=.9*target_w)
    peak=float(np.max(power))
    bands={str(b):_band_response(times,power,dt,target_w,start_s,b,dwell_s) for b in (10,20)}
    final=bands['10']['final_settling_s']
    return {'target_w':target_w,'start_s':start_s,'duration_s':end_s-start_s,
            'rise_to_90pct_target_s':float(times[reached[0]]-start_s) if len(reached) else None,
            'rise_threshold_w':.9*target_w,'peak_power_w':peak,
            'peak_overshoot_w':max(0.,peak-target_w),
            'max_undershoot_w':max(0.,target_w-float(np.min(power))),
            'mae_w':float(np.average(np.abs(power-target_w),weights=dt)),
            'bands':bands,'goal':{'band_w':10,'dwell_s':dwell_s,'settling_limit_s':GOAL_S,
                'meaning':f'Final settling entry strictly below 10 s, with at least {dwell_s:g} s in band and no later phase excursion',
                'met':final is not None and final<GOAL_S}}


def target_table_support(table,target_w):
    """Describe declared grid brackets, without claiming firmware lookup trust."""
    columns=table['columns']; max_w=(columns-1)*table['watt_increment']
    low=math.floor(target_w/table['watt_increment']); high=math.ceil(target_w/table['watt_increment'])
    cells=[]
    # Published sprint cue is 85 RPM with upward drift, so report both rows.
    for cadence in (85,90):
        row=(cadence-table['cadence_min'])//table['cadence_increment']
        for col in sorted({low,high}):
            in_grid=0<=row<table['rows'] and 0<=col<columns
            position,count=table['cells'][row*columns+col] if in_grid else (-32768,0)
            cells.append({'cadence_rpm':cadence,'watts':col*table['watt_increment'],
                          'in_grid':in_grid,'supported':in_grid and position!=-32768 and count>=2})
    return {'target_w':target_w,'table_max_w':max_w,'within_table_axis':target_w<=max_w,
            'declared_sprint_brackets_supported':all(c['supported'] for c in cells),'cells':cells,
            'meaning':'Observed support only; does not imply controller trust. Archived full remains the unchanged fixture covering the 45 declared training-grid cells. Targets above 870 W are outside this table axis.'}


def response_summary(trace,target_w,snapshots):
    signals={}
    for name,column in (('effective_plant',2),('delivered_sensor',14)):
        prefix=[]; start=0.
        for segment in probe():
            end=start+segment.duration_s
            prefix.append(phase_response(trace,segment.start_w,start,end,column=column))
            start=end
        recovery=phase_response(trace,100,RECOVERY_START_S,DURATION_S,column=column)
        # A rise threshold is not meaningful for a falling recovery step.
        recovery.pop('rise_to_90pct_target_s'); recovery.pop('rise_threshold_w')
        signals[name]={'low_power_prefix':prefix,
                       'sprint':phase_response(trace,target_w,SPRINT_START_S,RECOVERY_START_S,column=column),
                       'recovery':recovery}
    table=next(s['table'] for s in snapshots if s['time_s']==SPRINT_START_S)
    return {'signals':signals,'sprint_start_table_sha256':digest(table),
            'sprint_start_table_support':target_table_support(table,target_w)}


def load_fixture(path,profile,config):
    fixture=json.loads(path.read_text())
    if digest(fixture['table'])!=fixture['sha256']:
        raise ValueError('Fixture digest mismatch')
    if fixture['profile_sha256']!=hashlib.sha256(profile.read_bytes()).hexdigest():
        raise ValueError('Fixture was trained on a different plant profile')
    expected={'homed':True,'min_position':config.min_position,'max_position':config.max_position,
              'position_divisor':fixture['table']['position_divisor']}
    if fixture.get('coordinate_reference')!=expected:
        raise ValueError('Fixture coordinate reference differs or is missing')
    if not coverage(fixture['table'])['fully_supported_tested_range']:
        raise ValueError('Full fixture does not cover the original 45-cell grid')
    return fixture


def parser():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--firmware-root',type=Path,required=True)
    p.add_argument('--baseline-root',type=Path,required=True)
    p.add_argument('--candidate-root',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--fixtures',type=Path,help='Directory containing the original earned full.json')
    p.add_argument('--profile',type=Path,default=PACKAGE/'profiles/ride_20260927.json')
    p.add_argument('--targets',type=int,nargs='+',default=[500,700,1000])
    p.add_argument('--states',nargs='+',choices=('empty','full'),default=['empty','full'])
    p.add_argument('--sensitivities',type=int,nargs='+',choices=(3,5,10),default=[3,5,10])
    p.add_argument('--seeds',type=int,nargs='+',default=[7])
    baseline.arguments(p)
    return p


def execute(a,selection):
    workouts={target:diagnostic_workout(target) for target in a.targets}
    for values in (a.targets,a.states,a.sensitivities,a.seeds):
        if len(values)!=len(set(values)): raise ValueError('Duplicate matrix values are not allowed')
    if a.output.exists() and any(a.output.iterdir()): raise ValueError('Output must be new/empty')
    a.output.mkdir(parents=True,exist_ok=True)
    adapter,ainfo=load_adapter(a.firmware_root)
    profile=json.loads(a.profile.read_text()); config=BikeConfig(**profile['bike'])
    roots={'baseline':a.baseline_root,'candidate':a.candidate_root}
    if 'full' in a.states and a.fixtures is None:
        raise ValueError('Full state requires --fixtures')
    fixtures={state:None if state=='empty' else load_fixture(a.fixtures/'full.json',a.profile,config)
              for state in a.states}
    manifest={'status':'incomplete','experiment':EXPERIMENT,'baseline_selection':selection,
              'firmware':{k:source_provenance(v) for k,v in roots.items()},'adapter':ainfo,
              'simulator_sha256':file_fingerprint(PACKAGE,list(PACKAGE.rglob('*.py'))),
              'profile_sha256':hashlib.sha256(a.profile.read_bytes()).hexdigest(),'bike':asdict(config),
              'initial_fixtures':fixtures,'duration_s':DURATION_S,
              'absolute_budgets':DEFAULT_BUDGET,'relative_allowances':RELATIVE_ALLOWANCE,
              'goal':{'band_w':10,'dwell_s':DWELL_S,'settling_limit_s':GOAL_S},
              'coverage':'CPS/CSC packets, production FTMS, native controller; no Peloton cable window execution',
              'limitations':['Fitted plant is unchanged; high-position behavior may be outside recorded fit ranges.',
                  'Archived full is the unchanged original fixture covering 45 declared training-grid cells; it may contain other learned cells and does not imply high-target brackets.',
                  '1000 W is beyond the 870 W table axis and cannot have a full learned bracket.',
                  'Dwell diagnostics are new descriptive metrics; existing 20 W budgets and long-ride history are unchanged.',
                  'Short early-prefix screening does not establish middle/late long-ride behavior or hardware fidelity.'],
              'requested_cases':[{'target_w':t,'initial_state':s,'sensitivity':v,'seed':seed}
                  for s in a.states for v in a.sensitivities for seed in a.seeds for t in a.targets],
              'runs':[]}
    try:
        exes={k:adapter.build(a.output/k/'build',source_root=v,packet_ingress=True) for k,v in roots.items()}
        for state,fixture in fixtures.items():
            for sensitivity in a.sensitivities:
                for seed in a.seeds:
                    for target,workout in workouts.items():
                        case=f'early_{target}w_{state}_sensitivity{sensitivity}-{seed}'
                        diagnostics={}; scores={}; metadata={}
                        for variant in roots:
                            dest=a.output/variant/case
                            trace,meta,score,snapshots=run_one(adapter,exes[variant],config,profile,dest,workout,seed,
                                table=fixture['table'] if fixture else None,
                                windows=[{'name':'low_power_prefix','start_s':0,'duration_s':360}],
                                sensitivity=sensitivity,extra_snapshot_times=(SPRINT_START_S,))
                            meta['scenario_version']=EXPERIMENT
                            meta['diagnostic_sprint_target_w']=target
                            meta['coverage_note']=manifest['coverage']
                            diagnostic=response_summary(trace,target,snapshots)
                            for name,value in (('metadata',meta),('diagnostic',diagnostic)):
                                (dest/(name+'.json')).write_text(json.dumps(value,indent=2)+'\n')
                            diagnostics[variant]=diagnostic; scores[variant]=score; metadata[variant]=meta
                        bm,cm=metadata['baseline'],metadata['candidate']
                        for key in ('initial_table_sha256','cadence_plan_sha256','sensor_schedules','seed','sensitivity'):
                            if bm[key]!=cm[key]: raise RuntimeError(f'Paired input mismatch: {key}')
                        low={}
                        for signal,key in (('effective_plant','metrics'),('delivered_sensor','delivered_sensor_metrics')):
                            low[signal]=compare(scores['candidate']['windows'][0][key],scores['baseline']['windows'][0][key])
                        result={'case':case,'target_w':target,'initial_state':state,'sensitivity':sensitivity,'seed':seed,
                                'diagnostics':diagnostics,'metadata':metadata,'scores':scores,
                                'low_power_regression':low,'low_power_passed':all(x['passed'] for x in low.values()),
                                'low_power_relative_passed':all(x['relative_passed'] for x in low.values()),
                                'low_power_absolute_passed':all(x['absolute_passed'] for x in low.values())}
                        manifest['runs'].append(result)
                        print(f'{case}: low-power budget pass={result["low_power_passed"]}',flush=True)
                        (a.output/'high_power.json').write_text(json.dumps(manifest,indent=2)+'\n')
        manifest['status']='complete'
        for key in ('low_power_passed','low_power_relative_passed','low_power_absolute_passed'):
            manifest[key]=all(r[key] for r in manifest['runs'])
    except BaseException as exc:
        manifest['status']='failed'; manifest['error']=str(exc); raise
    finally:
        (a.output/'high_power.json').write_text(json.dumps(manifest,indent=2)+'\n')
    return 0 if manifest['low_power_passed'] else 1


def main(argv=None):
    a=parser().parse_args(argv); selection=baseline.select(a)
    with baseline.pinned_root(a.baseline_root,selection) as root:
        a.baseline_root=root
        return execute(a,selection)


if __name__=='__main__':
    raise SystemExit(main())
