"""WAL-aware snapshots and explicit maintenance-only atomic restore."""
import hashlib,json,os,shutil,sqlite3,time,uuid
from pathlib import Path
from .security import ident,digest_file

def metadata(path):
    c=sqlite3.connect('file:'+str(Path(path).absolute())+'?mode=ro',uri=True)
    try:
        integrity=c.execute('pragma integrity_check').fetchone()[0]
        fk=list(c.execute('pragma foreign_key_check'))
        tables=[r[0] for r in c.execute("select name from sqlite_master where type='table' and name not like 'sqlite_%' order by name")]
        counts={n:c.execute('select count(*) from "'+n.replace('"','""')+'"').fetchone()[0] for n in tables}
        schema=list(c.execute("select type,name,tbl_name,sql from sqlite_master where sql is not null order by type,name"))
        return {'integrity':integrity,'foreign_key_errors':len(fk),'counts':counts,'schema_hash':hashlib.sha256(json.dumps(schema).encode()).hexdigest(),'user_version':c.execute('pragma user_version').fetchone()[0]}
    finally:c.close()

class BackupStore:
    def __init__(self,database,root,retention=7,owner_uid=None,owner_gid=None):
        self.database=Path(database);self.root=Path(root);self.retention=max(2,retention);self.owner_uid=owner_uid;self.owner_gid=owner_gid
        self.root.mkdir(mode=0o700,parents=True,exist_ok=True)
        if self.root.is_symlink() or self.root.stat().st_mode & 0o077:raise ValueError('insecure_backup_directory')
    def backup(self,protect=()):
        if self.database.is_symlink():raise ValueError('database_symlink_denied')
        backup_id=f'b-{time.time_ns()}-{uuid.uuid4().hex[:12]}'
        path=self.root/backup_id;path.mkdir(mode=0o700);db=path/'database.sqlite3'
        src=sqlite3.connect('file:'+str(self.database.absolute())+'?mode=ro',uri=True);dest=sqlite3.connect(db)
        try:src.backup(dest)
        finally:src.close();dest.close()
        db.chmod(0o600);m=metadata(db)
        if m['integrity']!='ok' or m['foreign_key_errors']:raise ValueError('backup_integrity_failed')
        m.update({'backup_id':backup_id,'sha256':digest_file(db),'created_at':time.time(),'database_name':self.database.name})
        p=path/'metadata.json';p.write_text(json.dumps(m,indent=2));p.chmod(0o600)
        folders=sorted([p for p in self.root.iterdir() if p.is_dir() and not p.is_symlink()],reverse=True)
        for p in folders[self.retention:]:
            if p.name not in protect:shutil.rmtree(p)
        return m
    def restore(self,backup_id,maintenance=False):
        if not maintenance:raise ValueError('maintenance_grant_required')
        ident(backup_id);folder=self.root/backup_id
        if folder.is_symlink():raise ValueError('backup_symlink_denied')
        source=folder/'database.sqlite3';mp=folder/'metadata.json'
        if source.is_symlink() or mp.is_symlink():raise ValueError('backup_symlink_denied')
        m=json.loads(mp.read_text())
        if digest_file(source)!=m['sha256']:raise ValueError('backup_hash_mismatch')
        snap=metadata(source);current=metadata(self.database)
        if snap['integrity']!='ok' or snap['foreign_key_errors'] or snap['schema_hash']!=current['schema_hash'] or snap['user_version']!=current['user_version']:raise ValueError('restore_incompatible')
        safety=self.backup(protect=(backup_id,))
        # Caller has fenced all writers. WAL checkpoint first; discard only the fenced old WAL.
        c=sqlite3.connect(self.database,timeout=5)
        try:
            checkpoint=c.execute('pragma wal_checkpoint(TRUNCATE)').fetchone()
            if checkpoint[0]!=0:raise ValueError('writer_not_fenced')
        finally:c.close()
        dest=self.database.with_name(self.database.name+'.restore-new')
        fd=os.open(dest,os.O_CREAT|os.O_EXCL|os.O_WRONLY|os.O_NOFOLLOW,0o600)
        try:
            with os.fdopen(fd,'wb') as out,source.open('rb') as inp:
                shutil.copyfileobj(inp,out);out.flush();os.fsync(out.fileno())
            st=self.database.stat()
            if os.getuid()==0:os.chown(dest,self.owner_uid if self.owner_uid is not None else st.st_uid,self.owner_gid if self.owner_gid is not None else st.st_gid)
            for suffix in ('-wal','-shm'):
                p=Path(str(self.database)+suffix)
                if p.is_symlink():raise ValueError('wal_symlink_denied')
                p.unlink(missing_ok=True)
            os.replace(dest,self.database)
            fd=os.open(self.database.parent,os.O_DIRECTORY)
            try:os.fsync(fd)
            finally:os.close(fd)
        finally:dest.unlink(missing_ok=True)
        actual=metadata(self.database)
        if actual['integrity']!='ok' or actual['foreign_key_errors'] or actual['counts']!=snap['counts']:raise ValueError('restore_acceptance_failed')
        return {'restored_backup_id':backup_id,'safety_backup_id':safety['backup_id'],'acceptance':actual}
