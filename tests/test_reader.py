import json, tempfile, unittest
from pathlib import Path
from health_native.reader import HealthReader
S='|||HEALTH_NATIVE_ROW|||'
def w(p,n,b,e='2026-10-27T09:00:00+08:00'):(p/n).write_text(json.dumps({'export_date':e,'schema':'apple_health_native_columns_v1','column_separator':S,'batches':b}))
def b(t,src,st,en,val,u):return {'type':t,'count':str(len(st)),'sourceName':S.join(src),'startDate':S.join(st),'endDate':S.join(en),'value':S.join(val),'unit':S.join(u)}
class ReaderTests(unittest.TestCase):
 def test_two_snapshots_retain_union_and_revision(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d); a='2026-10-26T10:00:00+08:00'; z='2026-10-26T10:01:00+08:00'
   bstart='2026-10-26T10:02:00+08:00'; bend='2026-10-26T10:03:00+08:00'
   w(p,'health-native-2026-10-27_090000.json',[b('HKQuantityTypeIdentifierStepCount',['Phone','Phone'],[a,bstart],[z,bend],['100','200'],['count','count'])],'2026-10-27T09:00:00+08:00')
   w(p,'health-native-2026-10-27_100000.json',[b('HKQuantityTypeIdentifierStepCount',['Phone','Phone','Phone'],[a,bstart,'2026-10-26T11:00:00+08:00'],[z,bend,'2026-10-26T11:01:00+08:00'],['150','200','300'],['count']*3)],'2026-10-27T10:00:00+08:00')
   x=HealthReader([p]).read(); self.assertEqual(x['days'][0]['steps'],650); self.assertEqual(x['counts']['duplicate_samples'],2)
 def test_daily_old_day_is_retained_from_previous_export(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d); w(p,'health-native-2026-10-27_090000.json',[b('HKQuantityTypeIdentifierStepCount',['Phone'],['2026-10-26T10:00:00+08:00'],['2026-10-26T10:01:00+08:00'],['7'],['count'])],'2026-10-27T09:00:00+08:00'); w(p,'health-native-2026-10-28_090000.json',[b('HKQuantityTypeIdentifierStepCount',['Phone'],['2026-10-26T10:00:00+08:00'],['2026-10-26T10:01:00+08:00'],['7'],['count'])],'2026-10-28T09:00:00+08:00');
   # second file is not daily-scoped and must not erase the first sample
   x=HealthReader([p]).read(); self.assertEqual(x['days'][0]['steps'],7)
 def test_sleep_wake_day_and_empty_columns(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d); st=['2026-10-27T22:00:00+08:00','2026-10-27T23:00:00+08:00','2026-10-28T01:00:00+08:00']; en=['2026-10-27T23:00:00+08:00','2026-10-28T01:00:00+08:00','2026-10-28T02:00:00+08:00']; sl=b('HKCategoryTypeIdentifierSleepAnalysis',['','',''],st,en,['AsleepCore','AsleepDeep','AsleepREM'],['','','']); w(p,'health-native-latest.json',[sl],'2026-10-28T09:00:00+08:00'); x=HealthReader([p]).read(); self.assertEqual(x['days'][0]['date'],'2026-10-28'); self.assertEqual(x['days'][0]['sleep_minutes'],240)
 def test_generic_and_detailed_overlap_union(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d); st=['2026-10-27T22:00:00+08:00']*2; en=['2026-10-28T02:00:00+08:00']*2; sl=b('HKCategoryTypeIdentifierSleepAnalysis',['Phone','Phone'],st,en,['Asleep','AsleepCore'],['','']); w(p,'health-native-latest.json',[sl],'2026-10-28T09:00:00+08:00'); x=HealthReader([p]).read(); self.assertEqual(x['days'][0]['sleep_minutes'],240)
 def test_invalid_values_are_skipped_without_swallowing_good_row(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d); records=[]
   for value,unit in [('NaN','count'),('Infinity','count'),(True,'count'),(-1,'count'),(2,'bogus'),(3,'count')]: records.append({'type':'HKQuantityTypeIdentifierStepCount','sourceName':'Phone','startDate':'2026-10-26T10:00:00+08:00','endDate':'2026-10-26T10:01:00+08:00','value':value,'unit':unit})
   w(p,'health-native-latest.json',[]); (p/'health-native-latest.json').write_text(json.dumps({'export_date':'2026-10-27T09:00:00+08:00','schema':'apple_health_native_shortcut_v1','records':records})); x=HealthReader([p]).read(); self.assertEqual(x['days'][0]['steps'],3); self.assertEqual(x['counts']['invalid_samples'],5)
 def test_heart_rest_weight_units_and_cross_sources(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d); rec=[]
   for typ,src,val,unit in [('HKQuantityTypeIdentifierHeartRate','A',80,'bpm'),('HKQuantityTypeIdentifierRestingHeartRate','A',50,'count/min'),('HKQuantityTypeIdentifierBodyMass','A',1000,'g'),('HKQuantityTypeIdentifierBodyMass','B',2,'lb')]: rec.append({'type':typ,'sourceName':src,'startDate':'2026-10-26T10:00:00+08:00','endDate':'2026-10-26T10:01:00+08:00','value':val,'unit':unit})
   (p/'health-native-latest.json').write_text(json.dumps({'export_date':'2026-10-27T09:00:00+08:00','records':rec})); x=HealthReader([p]).read()[ 'days'][0]; self.assertEqual(x['heart_rate_avg_bpm'],80); self.assertEqual(x['resting_bpm'],50); self.assertEqual(x['weight_kg'],1.0)
 def test_records_validation_and_strict_names(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d); (p/'health-native-nope.json').write_text(json.dumps({'records':[]}))
   (p/'health-native-2026-10-27_090000.json').write_text(json.dumps({'export_date':'2026-10-27T09:00:00+08:00','records':[{'type':'HKQuantityTypeIdentifierStepCount','sourceName':'Phone','startDate':'2026-10-26T10:00:00+08:00','endDate':'2026-10-26T10:01:00+08:00','value':3,'unit':'count'}]}))
   x=HealthReader([p]).read(); self.assertEqual(x['days'][0]['steps'],3); self.assertEqual(x['source']['files_read'],1)
 def test_bad_timezone_unit_does_not_hide_good_file(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d); (p/'health-native-2026-10-27_090000.json').write_text(json.dumps({'export_date':'2026-10-27T09:00:00+08:00','records':[{'type':'HKQuantityTypeIdentifierStepCount','sourceName':'Phone','startDate':'2026-10-26T10:00:00','endDate':'2026-10-26T10:01:00','value':3,'unit':'count'}]}))
   (p/'health-native-latest.json').write_text(json.dumps({'export_date':'2026-10-27T10:00:00+08:00','records':[{'type':'HKQuantityTypeIdentifierStepCount','sourceName':'Phone','startDate':'2026-10-26T10:00:00+08:00','endDate':'2026-10-26T10:01:00+08:00','value':4,'unit':'bogus'}]}))
   x=HealthReader([p]).read(); self.assertEqual(x['days'],[]); self.assertGreaterEqual(x['counts']['invalid_samples'],1)
 def test_overlap_is_union_and_partial(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d); w(p,'health-native-latest.json',[b('HKQuantityTypeIdentifierStepCount',['Phone','Phone'],['2026-10-26T10:00:00+08:00','2026-10-26T10:30:00+08:00'],['2026-10-26T11:00:00+08:00','2026-10-26T11:30:00+08:00'],['10','20'],['count','count'])])
   x=HealthReader([p]).read(); self.assertEqual(x['days'][0]['steps'],10); self.assertIn('steps',x['days'][0]['partial_metrics'])
 def test_revision_and_sleep(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d); st='2026-10-26T23:00:00+08:00'; en='2026-10-27T07:00:00+08:00'; sl=b('HKCategoryTypeIdentifierSleepAnalysis',['Phone','Phone'],[st,st],['2026-10-27T01:00:00+08:00',en],['AsleepCore','InBed'],['',''])
   w(p,'health-native-old.json',[b('HKQuantityTypeIdentifierStepCount',['Phone'],[st],[en],['10'],['count']),sl],'2026-10-26'); w(p,'health-native-latest.json',[b('HKQuantityTypeIdentifierStepCount',['Phone'],[st],[en],['20'],['count']),sl]); x=HealthReader([p]).read(); self.assertEqual(x['days'][0]['steps'],20); self.assertEqual(x['days'][1]['sleep_minutes'],120.0)
 def test_probe_and_resting(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d); w(p,'health-native-probe.json',[]); w(p,'health-native-latest.json',[b('HKQuantityTypeIdentifierRestingHeartRate',['Watch'],['2026-10-26T10:00:00+08:00'],['2026-10-26T10:01:00+08:00'],['55'],['count/min'])]); x=HealthReader([p]).read(); self.assertEqual(x['days'][0]['resting_bpm'],55); self.assertEqual(x['source']['files_read'],1)
if __name__=='__main__':unittest.main()
