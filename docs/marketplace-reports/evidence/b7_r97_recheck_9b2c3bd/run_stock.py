import os,sys,socket,unittest
from pathlib import Path
root=Path(sys.argv[1]).resolve();sys.path.insert(0,str(root));os.chdir(root)
def audit(event,args):
 if event in ('socket.connect','socket.getaddrinfo'):raise AssertionError('Network forbidden in review')
sys.addaudithook(audit)
suite=unittest.defaultTestLoader.discover(str(root/'tests'),pattern='test_msp_marketplace*.py')
r=unittest.TextTestRunner(verbosity=1).run(suite)
modules={k:str(Path(m.__file__).resolve()) for k,m in list(sys.modules.items()) if k.startswith('apps.msp_marketplace_reports') and getattr(m,'__file__',None)}
assert modules and all(Path(p).is_relative_to(root) for p in modules.values()),modules
print('PROJECT_IMPORTS_PINNED',modules)
print('STOCK_TESTS',r.testsRun,'PASS' if r.wasSuccessful() else 'FAIL')
assert r.testsRun==140
sys.exit(0 if r.wasSuccessful() else 1)
