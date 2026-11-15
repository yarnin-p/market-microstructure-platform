"""Compact report whitespace without removing or sampling any research record."""
import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from market_lab.systematic_report import package


def encode(value):
    if isinstance(value,list):
        return '[\n'+',\n'.join(json.dumps(v,sort_keys=True,separators=(',',':')) for v in value)+'\n]'
    if isinstance(value,dict):
        return '{\n'+',\n'.join(json.dumps(k)+':'+(encode(v) if isinstance(v,list) else json.dumps(v,sort_keys=True,separators=(',',':'))) for k,v in sorted(value.items()))+'\n}'
    return json.dumps(value)


if __name__=='__main__':
    config=json.loads(Path('configs/task-002-2-systematic-v1.json').read_text())
    root=Path('data/runs',config['run_id']);dest=Path('reports',config['run_id'])
    for name in ['event-level-results','security_variation','statistical_results','denominators','cycle_metrics']:
        p=dest/(name+'.json');original=json.loads(p.read_text());text=encode(original)+'\n'
        assert json.loads(text)==original
        p.write_text(text)
    package(config,root,dest)
