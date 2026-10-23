"""Create safe deterministic fixtures. No malware, subprocess or network calls."""
import json,hashlib
from pathlib import Path
from d0.validate import digest
HERE=Path(__file__).parent
T='2026-10-23T10:00:00Z'
sha='a'*64
ref={'schema_version':'target-ref-v1','kind':'FILE','observed':{'path':'C:\\samples\\fixture.exe'},'identity_strength':'PARTIAL','verified_digest':{'algorithm':'sha256','value':sha},'snapshot':{'size_bytes':1024,'mtime_ns':123456789},'revalidation_required':True}
prov={'id':'ember_local','version':'0.1.0','adapter':'ember_adapter','runtime':'python'}
eff={'reads_target':True,'executes_foreign_code':False,'writes_filesystem':False,'mutates_target':False,'requires_human_approval':False,'cleanup_required':False}
limits={'timeout_ms':30000,'max_output_bytes':65536,'max_artifact_bytes':1048576,'max_concurrency':1}
spec={'schema_version':'d0-v1','tool_id':'static.ember_features','tool_version':'0.1.0','capability':'static.pe_features','description':'Read-only PE feature extraction on a verified file','input_schema_id':'ember-input-v1','output_schema_id':'ember-output-v1','provider':prov,'effects':eff,'limits':limits,'supported_targets':['FILE'],'enabled':True}
call={'schema_version':'d0-v1','call_id':'CALL-fixture0001','case_id':'CASE-fixture0001','expected_revision':1,'tool_id':spec['tool_id'],'tool_version':spec['tool_version'],'provider_id':prov['id'],'target_ref':ref,'arguments':{'feature_version':2},'reason':'Unknown reputation; static analysis required','requested_by':'workflow','requested_at':T,'budget':{'timeout_ms':10000,'max_output_bytes':4096}}
policy={'schema_version':'d0-v1','decision_id':'POL-fixture0001','call_id':call['call_id'],'case_id':call['case_id'],'expected_revision':1,'outcome':'ALLOW','reason_code':'static_readonly_allowed','reasons':['Target revalidation still required at execution'], 'effective_limits':limits,'policy_version':'policy-v1','evaluated_at':T}
receipt={'schema_version':'d0-v1','run_id':'RUN-fixture0001','call_id':call['call_id'],'case_id':call['case_id'],'tool_id':spec['tool_id'],'tool_version':spec['tool_version'],'provider':prov,'arguments_sha256':digest(call['arguments']),'target_binding':{'status':'VERIFIED','method':'opened_handle_identity_and_digest','observed_ref':ref,'verified_at':T},'started_at':T,'finished_at':'2026-10-23T10:00:01Z','outcome':'SUCCESS','cleanup':{'status':'NOT_REQUIRED','remaining_owned_resources':[]},'resources':{'duration_ms':1000,'output_bytes':128}}
obs={'facet':'ember_feature_count','status':'SUCCESS','coverage':'COMPLETE','value':2381,'limitations':[],'content_origin':'provider_output','trust_level':'UNTRUSTED_CONTENT','artifact_ref':None}
result={'schema_version':'d0-v1','run_id':receipt['run_id'],'call_id':call['call_id'],'case_id':call['case_id'],'target_ref':ref,'tool_id':spec['tool_id'],'tool_version':spec['tool_version'],'provider':prov,'status':'SUCCESS','observations':[obs],'receipt_sha256':digest(receipt),'raw_artifacts':[],'error':None}
workflow={'schema_version':'d0-v1','workflow_id':'WF-fixture0001','case_id':call['case_id'],'case_revision':1,'reputation':'UNKNOWN','phase':'REPUTATION','next_step':'STATIC_ANALYSIS','reason_code':'unknown_requires_static','agent_role':'FOLLOWUP_WITHIN_POLICY'}
approval={'schema_version':'d0-v1','request_id':'APR-fixture0001','case_id':call['case_id'],'expected_revision':1,'action_id':'ACTION-fixture0001','action_type':'QUARANTINE_FILE','target_ref':ref,'effect_summary':'Move file to controlled quarantine after fresh verification','risk':'HIGH','reason':'Analyst review required','expires_at':'2026-10-23T10:05:00Z','requested_at':T,'status':'PENDING'}
event={'schema_version':'d0-v1','request_id':approval['request_id'],'case_id':approval['case_id'],'action_id':approval['action_id'],'decision':'APPROVED','authenticated_subject':'local_analyst_fixture','authentication_method':'local_os_account','decided_at':'2026-10-23T10:01:00Z','expires_at':approval['expires_at'],'case_revision':1,'action_digest_sha256':sha}
for name,value in locals().copy().items():
 if name in ['target_ref','provider','effects','limits','tool_spec','tool_call','policy_decision','execution_receipt','observation','tool_result','workflow_decision','approval_request','approval_event']:
  pass
values={'target_ref':ref,'provider':prov,'effects':eff,'limits':limits,'tool_spec':spec,'tool_call':call,'policy_decision':policy,'execution_receipt':receipt,'observation':obs,'tool_result':result,'workflow_decision':workflow,'approval_request':approval,'approval_event':event}
for name,v in values.items():
 (HERE/(name+'.json')).write_text(json.dumps(v,indent=2,ensure_ascii=False)+'\n',encoding='utf8')
