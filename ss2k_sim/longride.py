"""Continuous 30–90 minute packet rides with auditable learned starting tables.

No controller logic or plant-to-table oracle lives here. Snapshots are taken through
read-only adapter calls; starting fixtures must come from production learning.
"""
import argparse
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import re
import numpy as np
from .adapter import load_adapter, source_provenance, file_fingerprint
from .cli import BASELINE_SHA, PACKAGE
from .model import BikeConfig
from .performance import summarize, compare, DEFAULT_BUDGET, RELATIVE_ALLOWANCE
from .runner import run
from .sampling import SensorSchedule
from .workout import Workout, Segment


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def probe():
    return [Segment(60, w, w, c) for w, c in
            ((180,85),(240,85),(150,85),(210,80),(210,90),(180,85))]


def long_workout(minutes, *, stress=False):
    if minutes not in (30, 60, 90):
        raise ValueError('Long rides must be 30, 60, or 90 minutes')
    # Repeated identical six-minute probes, separated by time-driven endurance
    # work. Every probe has a one-minute common lead-in to reduce entry effects.
    duration = minutes*60
    starts = (0, duration//2-180, duration-360)
    segments, cursor = [], 0
    for start in starts:
        while cursor < start:
            length = min(180, start-cursor)
            w,c = ((180,80),(210,85),(240,90))[(cursor//180)%3]
            segments.append(Segment(length,w,w,c)); cursor += length
        segments.extend(probe()); cursor += 360
    if stress:
        pause_start, pause_end = duration*.25+30, duration*.25+90
        split=[]; start=0
        for segment in segments:
            end=start+segment.duration_s
            points=sorted({start,end}|{t for t in (pause_start,pause_end) if start<t<end})
            for left,right in zip(points,points[1:]):
                split.append(Segment(right-left,segment.start_w,segment.end_w,
                                     0 if pause_start<=left<pause_end else segment.cadence_rpm))
            start=end
        segments=split
    return Workout(segments), [{'name': n, 'start_s': s, 'duration_s':360}
                                for n,s in zip(('early','middle','late'),starts)]


def coverage(table):
    cells = table['cells']
    required = []
    for cadence in (75,80,85,90,95):
        for watts in (150,180,210,240,270):
            r = (cadence-table['cadence_min'])//table['cadence_increment']
            c = watts//table['watt_increment']
            p,n = cells[r*table['columns']+c]
            required.append({'cadence_rpm':cadence,'watts':watts,'supported':p != -32768 and n >= 2})
    return {'supported_cells':sum(p != -32768 and n >= 2 for p,n in cells),
            'total_cells':len(cells), 'tested_range_supported':sum(x['supported'] for x in required),
            'tested_range_required':len(required), 'fully_supported_tested_range':all(x['supported'] for x in required),
            'tested_range_cells':required}


def observed_bridge(adapter, snapshots, *, initial_table=None, snapshot_times=(), pause_events=()):
    """One native process for the whole ride. No resets at probes or pauses."""
    class ObservedBridge(adapter.Bridge):
        def __init__(self,*args,**kwargs):
            super().__init__(*args,**kwargs)
            if initial_table is not None:
                self.load_power_table(initial_table)
            snapshots.append({'time_s':0, 'table':self.power_table()})
            self.observed = {0}
        def tick(self,now_ms,*args,**kwargs):
            now = (now_ms-1000)/1000
            for at, active in pause_events:
                if now == at: self.control(bytes([7]) if active else bytes([8,2]))
            if now in snapshot_times and now not in self.observed:
                snapshots.append({'time_s':now, 'table':self.power_table()}); self.observed.add(now)
            return super().tick(now_ms,*args,**kwargs)
    return ObservedBridge


def log_events(path):
    events=[]
    patterns={'learning_observation':'Raw observation:', 'table_insert_attempt':'Averaged Entry:',
              'table_gain_log':'(table)', 'fallback_gain_log':'(fallback',
              'trusted_seek_start':'Trusted table seek:', 'trusted_seek_extrapolated':'Trusted table seek (extrapolated):',
              'trusted_seek_end':'Trusted table seek ended', 'confidence_change':'Power table is now'}
    for line in Path(path).read_text().splitlines():
        m=re.match(r'\[(\d+)\]',line)
        if not m: continue
        for kind,text in patterns.items():
            if text in line: events.append({'time_s':(int(m[1])-1000)/1000,'kind':kind})
    return events


def window_summary(trace, windows, events, snapshots):
    results=[]
    for window in windows:
        start,end=window['start_s'],window['start_s']+window['duration_s']
        part=trace[(trace[:,0]>=start)&(trace[:,0]<end)].copy(); part[:,0]-=start
        score=summarize(part,360,Workout(probe()))
        delivered=part.copy(); delivered[:,2]=part[:,14]
        counts={kind:sum(e['kind']==kind and start<=e['time_s']<end for e in events)
                for kind in sorted({e['kind'] for e in events})}
        snapshot=next(s for s in snapshots if s['time_s']==start)
        results.append({**window,'metrics':score,'delivered_sensor_metrics':summarize(delivered,360,Workout(probe())),
                        'events':counts,'starting_table':coverage(snapshot['table']),
                        'seeking_seconds':float(np.sum(np.diff(np.r_[part[:,0],360])[part[:,8] != 0])),
                        'challenge_mae_after_lead_in_w':float(np.mean(np.abs(part[part[:,0]>=60,2]-part[part[:,0]>=60,1]))),
                        'table_sha256':digest(snapshot['table'])})
    return results


def run_one(adapter,exe,config,profile,output,workout,seed,*,table=None,windows=(),stress=False):
    snapshots=[]; duration=workout.duration
    # Stress is away from the repeated probes; pause/restart is a real FTMS procedure.
    outage=duration*.25
    power=SensorSchedule(1,.2,.1,dropouts=((outage,outage+12),) if stress else ())
    cadence=SensorSchedule(.25,.1)
    pauses=((outage+30,False),(outage+90,True)) if stress else ()
    factory=observed_bridge(adapter,snapshots,initial_table=table,
        snapshot_times=sorted({w['start_s'] for w in windows}|{round(t) for t in np.arange(60,duration,60)}),pause_events=pauses)
    trace,meta=run(workout,config,exe,output,seed=seed,initial_position=profile.get('start_position',7433),
        power_schedule=power,cadence_schedule=cadence,packet_ingress=True,bridge_factory=factory)
    final=json.loads((output/'power_table.json').read_text()); snapshots.append({'time_s':duration,'table':final})
    events=log_events(output/'firmware.log')
    meta['initial_table']='empty' if table is None else 'production-learned immutable fixture; RAM import, not flash persistence'
    meta['initial_table_sha256']=digest(snapshots[0]['table'])
    meta['initial_coverage']=coverage(snapshots[0]['table']); meta['final_coverage']=coverage(final)
    meta['controller_processes']=1; meta['state_resets_during_ride']=0
    meta['pause_events']=[{'time_s':t,'active':v} for t,v in pauses]
    meta['pause_model']='60-second zero-cadence rider cue with bounded deceleration/reacceleration; real FTMS pause/start packets are status-only in current production' if stress else None
    meta['event_count_meaning']='Production log observations and insertion attempts, not guaranteed accepted insertions; gain logs are sampled, not exhaustive lookup counts.'
    score=summarize(trace,duration,workout); delivered=trace.copy(); delivered[:,2]=trace[:,14]
    score['delivered_sensor_metrics']=summarize(delivered,duration,workout)
    score['windows']=window_summary(trace,windows,events,snapshots)
    for name,value in [('metadata',meta),('score',score),('learning_snapshots',snapshots),('learning_events',events)]:
        (output/(name+'.json')).write_text(json.dumps(value,indent=2)+'\n')
    return trace,meta,score,snapshots


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('command',choices=('train','compare'))
    p.add_argument('--firmware-root',type=Path,required=True); p.add_argument('--candidate-root',type=Path,required=True)
    p.add_argument('--baseline-root',type=Path); p.add_argument('--output',type=Path,required=True)
    p.add_argument('--fixtures',type=Path); p.add_argument('--profile',type=Path,default=PACKAGE/'profiles/ride_20260927.json')
    p.add_argument('--minutes',type=int,nargs='+',default=[30,60,90]); p.add_argument('--states',nargs='+',choices=('empty','partial','full'),default=['empty','partial','full'])
    p.add_argument('--seeds',type=int,nargs='+',default=[27]); p.add_argument('--stress',action='store_true')
    a=p.parse_args(argv)
    if a.output.exists() and any(a.output.iterdir()): raise ValueError('Output must be new/empty')
    a.output.mkdir(parents=True,exist_ok=True)
    adapter,ainfo=load_adapter(a.firmware_root); profile=json.loads(a.profile.read_text()); config=BikeConfig(**profile['bike'])
    roots={'candidate':a.candidate_root}
    if a.command=='compare':
        if a.baseline_root is None: raise ValueError('Paired long rides require baseline root')
        roots={'baseline':a.baseline_root,**roots}
    prov={k:source_provenance(v) for k,v in roots.items()}
    if 'baseline' in prov and (prov['baseline']['commit']!=BASELINE_SHA or prov['baseline']['dirty']): raise ValueError('Baseline must be clean pinned develop')
    manifest={'status':'incomplete','experiment':'continuous-long-ride-v1','firmware':prov,'adapter':ainfo,
        'simulator_sha256':file_fingerprint(PACKAGE,[x for x in PACKAGE.rglob('*.py')]),'profile_sha256':hashlib.sha256(a.profile.read_bytes()).hexdigest(),
        'bike':asdict(config),'absolute_budgets':DEFAULT_BUDGET,'relative_allowances':RELATIVE_ALLOWANCE,'runs':[],'requested_cases':[{'minutes':m,'initial_state':s,'seed':seed} for m in a.minutes for s in a.states for seed in a.seeds] if a.command=='compare' else [],'limitations':['Virtual packet/controller execution, no radio or ESP32 scheduler','RAM table import does not test flash save/load','Fully learned means measured support at all 25 tested-range grid cells, not the entire 300-cell firmware table','Window comparisons are descriptive; learning is not assumed to improve response','Same learned fixture for both firmware versions; candidate-trained fixture provenance retained']}
    try:
        exes={k:adapter.build(a.output/k/'build',source_root=v,packet_ingress=True) for k,v in roots.items()}
        if a.command=='train':
            workout=Workout([Segment(216,w,w,c) for c in (75,80,85,90,95) for w in (150,180,210,240,270)])
            trace,meta,score,snaps=run_one(adapter,exes['candidate'],config,profile,a.output/'training',workout,137)
            candidates=[s for s in snaps if 0<coverage(s['table'])['tested_range_supported']<coverage(s['table'])['tested_range_required']]
            if not candidates: raise RuntimeError('Training produced no partial table')
            partial=candidates[len(candidates)//3]
            fulls=[s for s in snaps if coverage(s['table'])['fully_supported_tested_range']]
            for name,snapshot in [('partial',partial)]+([('full',fulls[-1])] if fulls else []):
                fixture={'table':snapshot['table'],'sha256':digest(snapshot['table']),'training_time_s':snapshot['time_s'],
                    'coordinate_reference':{'homed':True,'min_position':config.min_position,'max_position':config.max_position,'position_divisor':snapshot['table']['position_divisor']},
                    'training_seed':137,'firmware':prov['candidate'],'adapter':ainfo,'coverage':coverage(snapshot['table']),
                    'training_segments':[asdict(s) for s in workout.segments], 'profile_sha256':manifest['profile_sha256'],
                    'provenance':'Unmodified production online learning from independently simulated CPS/CSC packets; no direct plant table injection'}
                (a.output/(name+'.json')).write_text(json.dumps(fixture,indent=2)+'\n')
            manifest['training']={'metadata':meta,'score':score,'full_fixture_created':bool(fulls)}
            if not fulls: manifest['warning']='Training did not earn full tested-range support; no full fixture fabricated'
        else:
            fixtures={}
            for state in a.states:
                if state=='empty': fixtures[state]=None; continue
                if a.fixtures is None: raise ValueError('Partial/full need --fixtures from train')
                fixture=json.loads((a.fixtures/(state+'.json')).read_text())
                if digest(fixture['table'])!=fixture['sha256']: raise ValueError('Fixture digest mismatch')
                if fixture['profile_sha256'] != manifest['profile_sha256']: raise ValueError('Fixture was trained on a different plant profile')
                expected_coordinates={'homed':True,'min_position':config.min_position,'max_position':config.max_position,'position_divisor':fixture['table']['position_divisor']}
                if fixture.get('coordinate_reference') != expected_coordinates: raise ValueError('Fixture coordinate reference differs or is missing')
                cov=coverage(fixture['table'])
                if state=='full' and not cov['fully_supported_tested_range']: raise ValueError('Full fixture does not cover tested range')
                if state=='partial' and not 0<cov['tested_range_supported']<cov['tested_range_required']: raise ValueError('Partial fixture must be partially supported')
                fixtures[state]=fixture
            manifest['initial_fixtures']=fixtures
            manifest['stress_enabled']=a.stress
            manifest['seeds']=a.seeds
            for minutes in a.minutes:
                workout,windows=long_workout(minutes,stress=a.stress)
                for state,fixture in fixtures.items():
                    for seed in a.seeds:
                        scores={}; metadata={}
                        for variant in roots:
                            dest=a.output/variant/f'long_{minutes}m_{state}-{seed}'
                            _,metadata[variant],scores[variant],_=run_one(adapter,exes[variant],config,profile,dest,workout,seed,
                                table=fixture['table'] if fixture else None,windows=windows,stress=a.stress)
                        result=compare(scores['candidate'],scores['baseline'])
                        sensor=compare(scores['candidate']['delivered_sensor_metrics'],scores['baseline']['delivered_sensor_metrics'])
                        result['passed'] &= sensor['passed']; result['reported_power_comparison']=sensor
                        result['window_comparisons']={}
                        for cw,bw in zip(scores['candidate']['windows'],scores['baseline']['windows']):
                            wc=compare(cw['metrics'],bw['metrics'])
                            wc['reported_power_comparison']=compare(cw['delivered_sensor_metrics'],bw['delivered_sensor_metrics'])
                            wc['passed'] &= wc['reported_power_comparison']['passed']
                            result['window_comparisons'][cw['name']]=wc
                        result['whole_ride_passed']=result['passed']
                        result['passed'] &= all(w['passed'] for w in result['window_comparisons'].values())
                        if metadata['candidate']['initial_table_sha256'] != metadata['baseline']['initial_table_sha256']:
                            raise RuntimeError('Baseline/candidate initial table snapshots differ')
                        manifest['runs'].append({'minutes':minutes,'initial_state':state,'seed':seed,'scores':scores,'metadata':metadata,**result})
                        print(f'{minutes}m {state} seed={seed}: {result["passed"]}',flush=True)
        manifest['status']='complete'
        manifest['passed']=all(r['passed'] for r in manifest['runs']) if manifest['runs'] else None
    except BaseException as exc:
        manifest['status']='failed'; manifest['error']=str(exc); raise
    finally:
        (a.output/'longride.json').write_text(json.dumps(manifest,indent=2)+'\n')
    return 1 if manifest['passed'] is False else 0

if __name__=='__main__':
    try:
        raise SystemExit(main())
    except (Exception, KeyboardInterrupt) as exc:
        print(f'LONG RIDE FAILED: {exc}')
        raise SystemExit(2)
