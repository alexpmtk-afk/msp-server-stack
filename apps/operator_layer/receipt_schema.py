"""Versioned model-receipt -> checkpoint contract. Raw receipts remain immutable.
Legacy v0 planning annotations are evidence, never authoritative journal fields.
"""
import copy
from .tasks import FIELDS,bounded
TOP={'schema_version','kind','plan','evidence','updates','thread_id'}
ANNOTATIONS={'mutations_performed','plan_approval','planning_only','source_instructions_executed','test_result'}
def normalize_receipt(raw):
 if not isinstance(raw,dict):raise ValueError('response_object_required')
 # Some models put the same boolean receipt claim at top level. Move it into
 # evidence without changing its truth value or bypassing independent readback.
 if 'verified' in raw:
  if raw.get('kind')!='complete' or type(raw['verified']) is not bool:raise ValueError('invalid_verifier_field')
  if not isinstance(raw.get('evidence',{}),dict):raise ValueError('response_field_type')
  if 'verified' in raw['evidence'] and raw['evidence']['verified'] != raw['verified']:raise ValueError('verifier_conflict')
  raw=copy.deepcopy(raw)
  v=raw.pop('verified')
  raw['evidence']={**raw.get('evidence',{}),'verified':v}
 if set(raw)-TOP:raise ValueError('unknown_response_field')
 version=raw.get('schema_version',0)
 if type(version) is not int or version not in (0,1):raise ValueError('unsupported_schema_version')
 if raw.get('kind') not in ('plan','checkpoint','complete','blocked'):raise ValueError('unknown_response_kind')
 r=copy.deepcopy(raw);r['schema_version']=1
 # Hermes may wrap a planning block list in exactly {"blocks": [...]}. Unwrap
 # only this known envelope; block validation and acceptance remain unchanged.
 if r['kind']=='plan' and isinstance(r.get('plan'),dict) and set(r['plan'])=={'blocks'}:
  r['plan']=r['plan']['blocks']
 updates=r.get('updates',{});evidence=r.get('evidence',{})
 # Planning notes from a model are not execution proof. Preserve legacy
 # list-shaped notes as non-authoritative metadata, only for plan receipts.
 if r['kind']=='plan' and isinstance(evidence,list):
  evidence={'unverified_planning_notes':evidence}
 if not isinstance(updates,dict) or not isinstance(evidence,dict):raise ValueError('response_field_type')
 # A textual production-state comment is not authoritative state. Keep it
 # as explicitly unverified evidence, never write it to journal state.
 if r['kind']=='complete' and isinstance(updates.get('production_state'),str):
  evidence['unverified_production_state_note']=updates['production_state']
  updates={k:v for k,v in updates.items() if k!='production_state'}
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
