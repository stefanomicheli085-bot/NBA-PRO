import json, os, time
from datetime import date, datetime, timedelta, timezone
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

BASE='https://site.api.espn.com/apis/site/v2/sports/basketball/nba'
SEASON_START=date(2026,10,1)
TODAY=date.today()
HEADERS={'User-Agent':'Mozilla/5.0 (compatible; NBA-PRO-free/1.0)','Accept':'application/json'}
def get_json(url):
    req=Request(url,headers=HEADERS)
    with urlopen(req,timeout=25) as r: return json.loads(r.read().decode('utf-8'))
def fnum(v):
    try:
        if v is None or v=='--' or v=='': return 0.0
        return float(str(v).replace('%',''))
    except (ValueError,TypeError): return 0.0
def extract_stat_map(labels, stats):
    out={}
    for i,label in enumerate(labels or []):
        if i<len(stats or []): out[str(label).strip().lower()]=stats[i]
    aliases={
      'MIN':['min','minutes'], 'PTS':['pts','points'], 'REB':['reb','rebounds'],
      'AST':['ast','assists'], 'STL':['stl','steals'], 'BLK':['blk','blocks'],
      'TOV':['to','tov','turnovers'], '3PM':['3pm','3pt','3-pt','three point field goals']
    }
    result={}
    for key, variants in aliases.items():
        val=next((out[a] for a in variants if a in out),None)
        if val is None:
            for k,v in out.items():
                if key=='3PM' and ('3pt' in k or '3-point' in k or '3pm' in k): val=v; break
        if val is not None:
            if key=='MIN' and ':' in str(val):
                parts=str(val).split(':'); val=fnum(parts[0])+fnum(parts[1])/60
            result[key]=fnum(val)
    return result

def parse_summary(summary, event):
    logs=[]; box=summary.get('boxscore') or {}
    comps=(event.get('competitions') or [{}])[0]
    date_text=(event.get('date') or comps.get('date') or '')[:10]
    matchup=event.get('name') or event.get('shortName') or ''
    competitors=comps.get('competitors') or []
    teams={c.get('team',{}).get('abbreviation',''):c.get('team',{}).get('displayName','') for c in competitors}
    for group in box.get('players') or []:
        team=group.get('team') or {}
        team_abbr=team.get('abbreviation','')
        for statgroup in group.get('statistics') or []:
            labels=statgroup.get('labels') or statgroup.get('keys') or []
            for athlete in statgroup.get('athletes') or []:
                person=athlete.get('athlete') or {}
                stats=athlete.get('stats') or []
                vals=extract_stat_map(labels,stats)
                if not vals or not person.get('displayName'): continue
                logs.append({'date':date_text,'game_id':str(event.get('id','')),'matchup':matchup,'player':person.get('displayName'),'team':team_abbr,'team_name':teams.get(team_abbr,team.get('displayName','')),'opponent':next((c.get('team',{}).get('abbreviation','') for c in competitors if c.get('team',{}).get('abbreviation','')!=team_abbr),''),**vals})
    return logs

def main():
    all_events={}; errors=[]
    d=SEASON_START
    while d<=TODAY:
        url=f'{BASE}/scoreboard?dates={d:%Y%m%d}&limit=1000'
        try:
            data=get_json(url)
            for e in data.get('events') or []: all_events[str(e.get('id'))]=e
        except Exception as ex: errors.append(f'scoreboard {d}: {ex}')
        d+=timedelta(days=1)
        time.sleep(.05)
    games=[]; player_logs=[]
    for eid,event in all_events.items():
        comp=(event.get('competitions') or [{}])[0]
        competitors=comp.get('competitors') or []
        games.append({'date':(event.get('date') or comp.get('date') or '')[:10],'game_id':eid,'matchup':event.get('name') or event.get('shortName') or '', 'status':(comp.get('status') or {}).get('type',{}).get('description','')})
        state=(comp.get('status') or {}).get('type',{}).get('state','')
        if state not in ('post','in'): continue
        try:
            summary=get_json(f'{BASE}/summary?event={eid}')
            player_logs.extend(parse_summary(summary,event))
        except Exception as ex: errors.append(f'summary {eid}: {ex}')
        time.sleep(.12)
    # De-duplicate logs by game/player, then aggregate full-season per-game stats.
    dedup={}
    for row in player_logs: dedup[(row.get('game_id'),row.get('player'))]=row
    player_logs=list(dedup.values())
    stats=['MIN','PTS','REB','AST','STL','BLK','TOV','3PM']
    accum={}
    for row in player_logs:
        p=row['player']; a=accum.setdefault(p,{'player':p,'team':row.get('team',''),'GP':0,**{k:0.0 for k in stats}})
        a['GP']+=1
        for k in stats:a[k]+=float(row.get(k,0) or 0)
        a['team']=row.get('team') or a['team']
    season=[]
    for a in accum.values():
        o={'player':a['player'],'team':a['team'],'GP':a['GP']}
        for k in stats:o[k+'_avg']=round(a[k]/a['GP'],2) if a['GP'] else 0
        season.append(o)
    season.sort(key=lambda x:x['player'].lower())
    out={'source':'ESPN public scoreboard/summary endpoints','updated_at':datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC'),'season_start':str(SEASON_START),'games':sorted(games,key=lambda x:x['date']),'player_logs':sorted(player_logs,key=lambda x:(x.get('date',''),x.get('player',''))),'player_season':season,'errors':errors[-30:]}
    os.makedirs('data',exist_ok=True)
    with open('data/auto.json','w',encoding='utf-8') as f: json.dump(out,f,ensure_ascii=False,separators=(',',':'))
    print(f"Saved {len(games)} games, {len(player_logs)} player game logs, {len(season)} players; errors={len(errors)}")
if __name__=='__main__': main()
