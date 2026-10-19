import importlib.util
import json
from pathlib import Path
import subprocess
from types import SimpleNamespace
import unittest
from unittest.mock import patch

spec=importlib.util.spec_from_file_location('mysql_container_provision',Path(__file__).resolve().parents[1]/'ansible/mysql-provision.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)

class ContainerCompatibilityTests(unittest.TestCase):
    def info(self):
        return dict(Config={'Image':'mysql:8.4','Labels':{'app':'dobhrap-mysql'}},Mounts=[{'Name':'dobhrap-mysql-data','Destination':'/var/lib/mysql'}],HostConfig={'PortBindings':{'3306/tcp':[{'HostIp':'127.0.0.1','HostPort':'3307'}]}})

    def test_cpu_failure_preserves_old_container_and_volume(self):
        calls=[]
        def run(argv,**kwargs):
            calls.append(argv)
            if argv[1:3]==['container','inspect']:return SimpleNamespace(returncode=0,stdout=json.dumps([self.info()]),stderr='')
            if argv[1]=='logs':return SimpleNamespace(returncode=0,stdout='',stderr='Fatal glibc error: CPU does not support x86-64-v2')
            if argv[1]=='volume':return SimpleNamespace(returncode=1,stdout='',stderr='')
            return SimpleNamespace(returncode=0,stdout='',stderr='')
        with patch.object(module.subprocess,'run',side_effect=run),patch.object(module,'APP_CONFIG',SimpleNamespace(exists=lambda:False)),patch.object(module,'Path',return_value=SimpleNamespace(exists=lambda:False)):
            module.prepare_container()
        self.assertTrue(any(c[1]=='rename' for c in calls))
        self.assertFalse(any(c[1]=='rm' for c in calls))
        self.assertFalse(any(c[1:3]==['volume','rm'] for c in calls))
        probe=next(i for i,c in enumerate(calls) if c[1]=='run')
        stop=next(i for i,c in enumerate(calls) if c[1]=='stop')
        self.assertLess(probe,stop)

    def test_unrelated_container_is_rejected(self):
        info=self.info();info['Config']['Labels']['app']='other'
        with patch.object(module.subprocess,'run',return_value=SimpleNamespace(returncode=0,stdout=json.dumps([info]))):
            with self.assertRaisesRegex(AssertionError,'label'):module.prepare_container()

    def test_failed_replacement_probe_never_stops_original(self):
        calls=[]
        def run(argv,**kwargs):
            calls.append(argv)
            if argv[1:3]==['container','inspect']:return SimpleNamespace(returncode=0,stdout=json.dumps([self.info()]),stderr='')
            if argv[1]=='logs':return SimpleNamespace(returncode=0,stdout='CPU does not support x86-64-v2',stderr='')
            if argv[1]=='run':raise subprocess.CalledProcessError(127,argv)
            return SimpleNamespace(returncode=0,stdout='',stderr='')
        with patch.object(module.subprocess,'run',side_effect=run),patch.object(module,'APP_CONFIG',SimpleNamespace(exists=lambda:False)),patch.object(module,'Path',return_value=SimpleNamespace(exists=lambda:False)):
            with self.assertRaises(subprocess.CalledProcessError):module.prepare_container()
        self.assertFalse(any(c[1] in ('stop','rename','update') for c in calls))
