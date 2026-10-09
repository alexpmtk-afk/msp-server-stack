import unittest
from apps.operator_layer.github import GitHubBroker, validate_branch, validate_files, merge_gate

SHA='a'*40
POLICY={'repository':'alexpmtk-afk/msp-server-stack','required_checks':{'unit':15368,'gitleaks':15368},'owner_login':'alexpmtk-afk'}
class GitHubTests(unittest.TestCase):
    def test_ref_guard(self):
        validate_branch('hermes/task-1/change')
        for b in ['main','hermes/../main','hermes/a.lock','hermes/a;whoami']:
            with self.assertRaises(ValueError):validate_branch(b)
    def test_path_guard(self):
        for p in ['../etc/passwd','.github/workflows/a.yml','a/.git/config','/etc/passwd']:
            with self.assertRaises(ValueError):validate_files({p:'x'})
    def test_gate_ordinary_pass(self):
        merge_gate(POLICY,{'head':{'sha':SHA},'base':{'ref':'main'},'draft':False,'state':'open'},SHA,['apps/msp_data_sync/sync.py'],self.checks(),[])
    def checks(self):return [{'name':k,'head_sha':SHA,'status':'completed','conclusion':'success','app':{'id':15368}} for k in POLICY['required_checks']]
    def test_missing_checks_denied(self):
        with self.assertRaises(ValueError):merge_gate(POLICY,{'head':{'sha':SHA},'base':{'ref':'main'},'draft':False,'state':'open'},SHA,['README.md'],[],[])
    def test_stale_and_spoofed_denied(self):
        for checks in [[{**x,'head_sha':'b'*40} for x in self.checks()],[{**x,'app':{'id':1}} for x in self.checks()],[{**x,'conclusion':'skipped'} for x in self.checks()]]:
            with self.assertRaises(ValueError):merge_gate(POLICY,{'head':{'sha':SHA},'base':{'ref':'main'},'draft':False,'state':'open'},SHA,['README.md'],checks,[])
    def test_protected_needs_current_owner_approval(self):
        pr={'head':{'sha':SHA},'base':{'ref':'main'},'draft':False,'state':'open'}
        with self.assertRaises(ValueError):merge_gate(POLICY,pr,SHA,['AGENTS.md'],self.checks(),[])
        merge_gate(POLICY,pr,SHA,['AGENTS.md'],self.checks(),[{'user':{'login':'alexpmtk-afk'},'state':'APPROVED','commit_id':SHA}])
    def test_wrong_repo_and_unknown_fields_rejected_before_network(self):
        b=GitHubBroker(POLICY,None)
        with self.assertRaises(ValueError):b.execute('create_branch',{'branch':'hermes/test/x','base_sha':SHA,'shell':'id'})
        with self.assertRaises(ValueError):b.execute('delete_repository',{})
if __name__=='__main__':unittest.main()
