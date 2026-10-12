"""Shared time-driven ride and sensor stress scenarios."""
from .workout import Workout, Segment
from .sampling import SensorSchedule

def scenarios():
    step = Workout([Segment(60, 150, 150, 85), Segment(60, 250, 250, 85),
                    Segment(60, 160, 160, 85), Segment(60, 180, 180, 85)])
    cadence = Workout([Segment(60, 200, 200, 90), Segment(60, 200, 200, 65),
                       Segment(60, 200, 200, 105), Segment(60, 200, 200, 85)])
    ramp = Workout([Segment(45, 120, 120, 85), Segment(90, 120, 300, 85),
                    Segment(45, 300, 300, 85), Segment(60, 300, 120, 85)])
    normal = SensorSchedule()
    return [
        ('steps', step, normal, SensorSchedule(.25)),
        ('ramp', ramp, normal, SensorSchedule(.25)),
        ('cadence_shift', cadence, normal, SensorSchedule(.25)),
        ('slow_power', step, SensorSchedule(2, .35, .1), SensorSchedule(.25, .1)),
        ('fast_power_slow_cadence', cadence, SensorSchedule(.25, .1), SensorSchedule(2, .4)),
        ('sensor_outage', step, SensorSchedule(1, .2, .1, dropouts=((90, 98),)),
         SensorSchedule(.5, .1, dropouts=((150, 158),))),
    ]
