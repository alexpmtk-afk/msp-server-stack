"""Versioned model-receipt -> checkpoint contract. Raw receipts remain immutable.
Legacy v0 planning annotations are evidence, never authoritative journal fields.
"""
import copy
from .tasks import FIELDS,bounded
TOP={'schema_version','kind','plan','evidence','updates','thread_id'}
ANNOTATIONS={'mutations_performed','plan_approval','planning_only','source_instructions_executed','test_result'}
def normalize_receipt(raw):
 if not isinstance(raw,dict):raise ValueError('response_object_required')
 if set(raw)-TOP:raise ValueError('unknown_response_field')
 version=raw.get('schema_version',0)
 if type(version) is not int or version not in (0,1):raise ValueError('unsupported_schema_version')
 if raw.get('kind') not in ('plan','checkpoint','complete','blocked'):raise ValueError('unknown_response_kind')
 r=copy.deepcopy(raw);r['schema_version']=1
 updates=r.get('updates',{});evidence=r.get('evidence',{})
 if not isinstance(updates,dict) or not isinstance(evidence,dict):raise ValueError('response_field_type')
 annotations={k:v for k,v in updates.items() if k in ANNOTATIONS}
 if annotations:
  if version!=0 or r['kind']!='plan':raise ValueError('planning_annotation_not_allowed')
  for k,v in annotations.items():
   if k in ('mutations_performed','planning_only','source_instructions_executed'):
    if type(v) is not bool:raise ValueError('planning_annotation_type')
   elif not isinstance(v,str):raise ValueError('planning_annotation_type')
  if 'planning_metadata' in evidence:raise ValueError('planning_metadata_conflict')
  evidence['planning_metadata']=annotations
 updates={k:v for k,v in updates.items() if k not in annotations}
 if set(updates)-FIELDS:raise ValueError('unknown_checkpoint_update')
 for k,v in updates.items():
  if k=='production_state':
   if not isinstance(v,dict):raise ValueError('checkpoint_update_type')
  elif v is not None and not isinstance(v,str):raise ValueError('checkpoint_update_type')
 if 'thread_id' in r and not isinstance(r['thread_id'],str):raise ValueError('thread_id_type')
 if r['kind']=='plan' and (not isinstance(r.get('plan'),list) or not r['plan']):raise ValueError('plan_required')
 r['evidence']=evidence;r['updates']=updates;bounded(r);return r
