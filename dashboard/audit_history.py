"""Verify compiled production function bodies match each selected Git revision."""
import argparse
import hashlib
import json
import pathlib
import sys
import re

parser=argparse.ArgumentParser()
parser.add_argument('--adapter',type=pathlib.Path,required=True)
parser.add_argument('--candidate',type=pathlib.Path,required=True)
parser.add_argument('--build',type=pathlib.Path,required=True)
parser.add_argument('--label',required=True)
parser.add_argument('--output',type=pathlib.Path,required=True)
args=parser.parse_args()
from ss2k_sim.adapter import load_adapter
adapter,info=load_adapter(args.adapter)

checks = {
    'src/Power_Table.cpp': ['void PowerBuffer::set(', 'void PowerBuffer::clearSamples(', 'void PowerBuffer::reset(', 'int PowerBuffer::getReadings(', 'void PowerTable::processPowerValue(', 'void PowerTable::newEntry(', 'void PowerTable::setStepperMinMax(', 'void PowerTable::clearRuntime(', 'bool PowerTable::reset('],
    'src/Stepper.cpp': ['void SS2K::moveStepper(', 'static int getScaledHomingSensitivity(', 'static HomingSgBaseline getHomingSgBaseline(', 'bool SS2K::_findEndStop('],
    'src/BLE_Client.cpp': ['static void notifyCB(', 'static bool subscribeToCharacteristic(', 'bool subscribeToAllNotifications(', 'void MyClientCallback::onDisconnect(', 'void SpinBLEAdvertisedDevice::set(', 'void SpinBLEAdvertisedDevice::clearState(', 'void SpinBLEAdvertisedDevice::reset(', 'bool SpinBLEAdvertisedDevice::enqueueData(', 'NotifyData SpinBLEAdvertisedDevice::dequeueData('],
    'src/BLE_Common.cpp': ['void BLECommunications('],
    'src/SensorCollector.cpp': ['void collectAndSet('],
    'src/BLE_Fitness_Machine_Service.cpp': ['void BLE_Fitness_Machine_Service::processFTMSWrite('],
}
optional = {'void PowerBuffer::clearSamples(', 'void PowerTable::clearRuntime(', 'static bool subscribeToCharacteristic('}
results = []
for label in [args.label]:
    root = args.candidate
    build = args.build
    compiled = (build/'erg_bridge.cpp').read_text()
    rows = []
    for filename, signatures in checks.items():
        source = (root/filename).read_text()
        for sig in signatures:
            if sig not in source and sig in optional:
                rows.append({'file': filename, 'signature': sig, 'status': 'absent_in_selected_revision'})
                continue
            body = adapter.function(source, sig)
            assert body in compiled, (label, filename, sig)
            rows.append({'file': filename, 'signature': sig, 'status': 'byte_exact', 'sha256': hashlib.sha256(body.encode()).hexdigest()})
    source = (root/'src/ERG_Mode.cpp').read_text()
    for header in ['"SS2KLog.h"', '"Main.h"', '"Power_Table.h"', '"BLE_Custom_Characteristic.h"', '<LittleFS.h>']:
        source = source.replace('#include '+header, '')
    assert source in compiled, (label, 'entire ERG module')
    rows.append({'file': 'src/ERG_Mode.cpp', 'status': 'byte_exact_except_peripheral_include_removal', 'sha256': hashlib.sha256(source.encode()).hexdigest()})
    helper = (root/'src/PowerTable_Helpers.cpp').read_text()
    if (build/'PowerTable_Helpers.cpp').exists():
        assert 'unsigned long millis() {' in helper
        expected = helper.replace(adapter.function(helper, 'unsigned long millis('), '')
        assert expected == (build/'PowerTable_Helpers.cpp').read_text()
        rows.append({'file': 'src/PowerTable_Helpers.cpp', 'status': 'byte_exact_except_native_test_wall_clock_stub_removal'})
    else:
        rows.append({'file': 'src/PowerTable_Helpers.cpp', 'status': 'compiled_directly_from_clean_revision'})
    for parser in (root/'lib/SS2K/src/sensors').glob('*.cpp'):
        text = parser.read_text()
        text = re.sub(r'std::chrono::duration_cast<std::chrono::milliseconds>\(\s*std::chrono::steady_clock::now\(\).time_since_epoch\(\)\s*\).count\(\)', 'clockMs', text)
        expected = '#include <cstdint>\nextern uint32_t clockMs;\n'+text
        assert expected == (build/('virtual_ble_'+parser.name)).read_text()
        rows.append({'file': str(parser.relative_to(root)), 'status': 'byte_exact_except_virtual_clock_seam'})
    results.append({'label': label, 'passed': True, 'checks': rows})
out = {'adapter_fingerprint': info['sha256'], 'passed': True, 'revisions': results}
args.output.write_text(json.dumps(out, indent=2)+'\n')
print('Production source audit passed:', ', '.join(r['label'] for r in results))
