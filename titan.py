"""
TITAN ULTIMATE v5.0 - Real Trade Journal + Hourly Check + Narrative
"""
import math, requests, asyncio, os, json
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (Application, CommandHandler, MessageHandler,
                          filters, ContextTypes, CallbackQueryHandler)

BOT_TOKEN  = os.environ.get("BOT_TOKEN",  "YOUR_BOT_TOKEN_HERE")
ALLOWED_ID = int(os.environ.get("ALLOWED_ID", "123456789"))
TD_KEY     = os.environ.get("TD_KEY",     "YOUR_TWELVEDATA_API_KEY")
SCAN_INTERVAL = 300
TRADES_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "trades.json")

def auth(u): return u.effective_user.id == ALLOWED_ID

SYMBOLS = {
    'btc':'BTC/USD','eth':'ETH/USD','bnb':'BNB/USD','sol':'SOL/USD',
    'xrp':'XRP/USD','ada':'ADA/USD','doge':'DOGE/USD','avax':'AVAX/USD',
    'link':'LINK/USD','ltc':'LTC/USD','dot':'DOT/USD','matic':'MATIC/USD',
    'shib':'SHIB/USD','trx':'TRX/USD','atom':'ATOM/USD','uni':'UNI/USD',
    'near':'NEAR/USD','ftm':'FTM/USD','arb':'ARB/USD','op':'OP/USD',
    'inj':'INJ/USD','sui':'SUI/USD','apt':'APT/USD','pepe':'PEPE/USD',
    'wld':'WLD/USD','floki':'FLOKI/USD',
    'eurusd':'EUR/USD','gbpusd':'GBP/USD','usdjpy':'USD/JPY',
    'audusd':'AUD/USD','usdcad':'USD/CAD','usdchf':'USD/CHF',
    'nzdusd':'NZD/USD','eurgbp':'EUR/GBP','eurjpy':'EUR/JPY',
    'gbpjpy':'GBP/JPY','eurcad':'EUR/CAD','gbpcad':'GBP/CAD',
    'audcad':'AUD/CAD','audchf':'AUD/CHF','audjpy':'AUD/JPY',
    'chfjpy':'CHF/JPY','eurnzd':'EUR/NZD','gbpaud':'GBP/AUD',
    'gbpnzd':'GBP/NZD','nzdjpy':'NZD/JPY',
    'gold':'XAU/USD','xauusd':'XAU/USD','silver':'XAG/USD',
    'oil':'WTI/USD','wti':'WTI/USD','brent':'BRENT/USD',
    'nas100':'NDX/USD','sp500':'SPX/USD','dow':'DJI/USD','dax':'DAX/EUR',
}
SCAN_LIST=['BTC/USD','ETH/USD','SOL/USD','BNB/USD','XRP/USD',
           'EUR/USD','GBP/USD','USD/JPY','XAU/USD','GBP/JPY']
WATCHLIST=set()
scanner_active=False
scanner_tf='15min'
last_signals={}
pending_log={}  # message_id -> trade data, waiting for user confirmation

def resolve(s):
    s=s.lower().strip().replace('/','').replace('-','').replace('_','').replace(' ','')
    if s in SYMBOLS: return SYMBOLS[s]
    if len(s)==6: return s[:3].upper()+'/'+s[3:].upper()
    return s.upper()+'/USD'

def get_session():
    h=datetime.utcnow().hour; s=[]
    if 22<=h or h<7:  s.append("🌏 Tokyo")
    if 7<=h<16:       s.append("🇬🇧 London")
    if 13<=h<22:      s.append("🇺🇸 New York")
    if 13<=h<16:      s.append("⚡ Overlap!")
    return " | ".join(s) if s else "🌙 خاموش"

def session_quality():
    h=datetime.utcnow().hour
    if 13<=h<16: return "🟢 عالی"
    if 7<=h<13 or 16<=h<22: return "🟡 متوسط"
    return "🔴 ضعیف"

# ════════════════════════════════
#  دفترچه معاملات (Trade Journal)
# ════════════════════════════════
def load_trades():
    if os.path.exists(TRADES_FILE):
        try:
            with open(TRADES_FILE,'r',encoding='utf-8') as f: return json.load(f)
        except: return []
    return []

def save_trades(trades):
    try:
        with open(TRADES_FILE,'w',encoding='utf-8') as f:
            json.dump(trades,f,ensure_ascii=False,indent=2)
    except Exception as e: print(f"خطا در ذخیره: {e}")

def log_trade(symbol,direction,entry,sl,tp1,tp2,tp3,tp4,tf,strength,session):
    trades=load_trades()
    tid=(max([t['id'] for t in trades]) if trades else 0)+1
    trade={'id':tid,'symbol':symbol,'direction':direction,'entry':entry,'sl':sl,
           'tp1':tp1,'tp2':tp2,'tp3':tp3,'tp4':tp4,'tf':tf,'strength':strength,
           'session':session,'status':'OPEN',
           'opened_at':datetime.now().isoformat(),'closed_at':None}
    trades.append(trade); save_trades(trades)
    return tid

def get_session_for_trade():
    """سشن فعلی رو برمیگردونه تا موقع ثبت معامله ذخیره بشه"""
    h=datetime.utcnow().hour
    if 13<=h<16: return "Overlap"
    if 7<=h<16: return "London"
    if 13<=h<22: return "NewYork"
    if 22<=h or h<7: return "Tokyo"
    return "Other"

def get_stats():
    """آمار کامل و دقیق فقط از معاملات واقعی ثبت‌شده"""
    trades=load_trades()
    closed=[t for t in trades if t['status']!='OPEN']
    open_t=[t for t in trades if t['status']=='OPEN']
    total=len(closed)

    if total==0:
        return {
            'total':len(trades),'open':len(open_t),'closed':0,
            'tp1':0,'tp2':0,'tp3':0,'tp4':0,'sl':0,'wr':0,
            'max_win_streak':0,'max_loss_streak':0,'avg_duration_hours':0,
            'best_session':'—','worst_session':'—','session_stats':{},
            'has_data':False
        }

    tp1=len([t for t in closed if t['status']=='TP1'])
    tp2=len([t for t in closed if t['status']=='TP2'])
    tp3=len([t for t in closed if t['status']=='TP3'])
    tp4=len([t for t in closed if t['status']=='TP4'])
    sl=len([t for t in closed if t['status']=='SL'])
    wins=tp1+tp2+tp3+tp4
    wr=(wins/total*100) if total>0 else 0

    closed_sorted=sorted(closed,key=lambda t: t.get('closed_at') or '')
    max_win_streak=0; max_loss_streak=0; cur_win=0; cur_loss=0
    for t in closed_sorted:
        if str(t['status']).startswith('TP'):
            cur_win+=1; cur_loss=0
            max_win_streak=max(max_win_streak,cur_win)
        else:
            cur_loss+=1; cur_win=0
            max_loss_streak=max(max_loss_streak,cur_loss)

    durations=[]
    for t in closed_sorted:
        try:
            o=datetime.fromisoformat(t['opened_at'])
            c=datetime.fromisoformat(t['closed_at'])
            durations.append((c-o).total_seconds()/3600)
        except: pass
    avg_duration=sum(durations)/len(durations) if durations else 0

    session_stats={}
    for t in closed:
        s=t.get('session','Other')
        if s not in session_stats: session_stats[s]={'wins':0,'total':0}
        session_stats[s]['total']+=1
        if str(t['status']).startswith('TP'): session_stats[s]['wins']+=1
    for s in session_stats:
        st=session_stats[s]
        st['wr']=(st['wins']/st['total']*100) if st['total']>0 else 0

    valid_sessions={s:v for s,v in session_stats.items() if v['total']>=2}
    if valid_sessions:
        best=max(valid_sessions.items(),key=lambda x:x[1]['wr'])
        worst=min(valid_sessions.items(),key=lambda x:x[1]['wr'])
        best_session_txt=f"{best[0]} ({best[1]['wr']:.0f}% در {best[1]['total']} معامله)"
        worst_session_txt=f"{worst[0]} ({worst[1]['wr']:.0f}% در {worst[1]['total']} معامله)"
    else:
        best_session_txt="هنوز داده کافی نیست (حداقل ۲ معامله در هر سشن لازمه)"
        worst_session_txt="هنوز داده کافی نیست"

    return {
        'total':len(trades),'open':len(open_t),'closed':total,
        'tp1':tp1,'tp2':tp2,'tp3':tp3,'tp4':tp4,'sl':sl,'wr':wr,
        'max_win_streak':max_win_streak,'max_loss_streak':max_loss_streak,
        'avg_duration_hours':avg_duration,
        'best_session':best_session_txt,'worst_session':worst_session_txt,
        'session_stats':session_stats,'has_data':True
    }

async def check_open_trades(app):
    """چک میکنه معاملات باز به TP1/2/3/4 یا SL رسیدن یا نه"""
    trades=load_trades()
    open_t=[t for t in trades if t['status']=='OPEN']
    if not open_t: return
    changed=False
    for t in open_t:
        try:
            cs=fetch(t['symbol'],interval='5min',count=5)
            curr=cs[-1]['c']
            hi=max(c['h'] for c in cs[-3:]); lo=min(c['l'] for c in cs[-3:])
            d=t['direction']
            new_status=None
            if d=='BUY':
                if lo<=t['sl']: new_status='SL'
                elif hi>=t.get('tp4',float('inf')): new_status='TP4'
                elif hi>=t['tp3']: new_status='TP3'
                elif hi>=t['tp2']: new_status='TP2'
                elif hi>=t['tp1']: new_status='TP1'
            else:
                if hi>=t['sl']: new_status='SL'
                elif lo<=t.get('tp4',float('-inf')): new_status='TP4'
                elif lo<=t['tp3']: new_status='TP3'
                elif lo<=t['tp2']: new_status='TP2'
                elif lo<=t['tp1']: new_status='TP1'
            if new_status:
                t['status']=new_status; t['closed_at']=datetime.now().isoformat(); changed=True
                emoji="✅" if new_status.startswith('TP') else "🛑"
                try:
                    o=datetime.fromisoformat(t['opened_at'])
                    dur=(datetime.now()-o).total_seconds()/3600
                    await app.bot.send_message(chat_id=ALLOWED_ID,
                        text=f"{emoji} معامله #{t['id']} {t['symbol']} بسته شد!\n"
                             f"نتیجه: {new_status}\nقیمت فعلی: {curr:.6g}\n"
                             f"مدت معامله: {dur:.1f} ساعت")
                except: pass
        except: pass
    if changed: save_trades(trades)

# ════════════════════════════════
#  دریافت داده
# ════════════════════════════════
def fetch(sym, interval='15min', count=200):
    r=requests.get("https://api.twelvedata.com/time_series",
        params={"symbol":sym,"interval":interval,"outputsize":count,"apikey":TD_KEY},timeout=15)
    d=r.json()
    if 'values' not in d: raise ValueError(d.get('message','سیمبول پیدا نشد'))
    return [{'t':v['datetime'],'o':float(v['open']),'h':float(v['high']),
             'l':float(v['low']),'c':float(v['close']),'v':float(v.get('volume',0))}
            for v in reversed(d['values'])]

# ════════════════════════════════
#  اندیکاتورها (None-safe)
# ════════════════════════════════
def safe(v, default=0.0): return float(v) if v is not None else default

def ema(v, p):
    r=[None]*len(v); k=2/(p+1)
    for i in range(len(v)):
        if i < p-1: pass
        elif i == p-1:
            vals=[x for x in v[i-p+1:i+1] if x is not None]
            r[i]=sum(vals)/len(vals) if vals else None
        else:
            if r[i-1] is not None and v[i] is not None: r[i]=v[i]*k+r[i-1]*(1-k)
            elif r[i-1] is not None: r[i]=r[i-1]
    return r

def sma(v, p):
    res=[]
    for i in range(len(v)):
        if i<p-1: res.append(None)
        else:
            vals=[x for x in v[i-p+1:i+1] if x is not None]
            res.append(sum(vals)/len(vals) if vals else None)
    return res

def rsi(c, p=14):
    r=[None]*len(c)
    for i in range(p,len(c)):
        try:
            d=[c[j]-c[j-1] for j in range(i-p+1,i+1) if c[j] is not None and c[j-1] is not None]
            if not d: continue
            ag=sum(x for x in d if x>0)/p; al=sum(abs(x) for x in d if x<0)/p or 1e-9
            r[i]=round(100-100/(1+ag/al),2)
        except: pass
    return r

def macd_f(c,f=12,s=26,sg=9):
    ef=ema(c,f); es=ema(c,s)
    ml=[ef[i]-es[i] if ef[i] is not None and es[i] is not None else None for i in range(len(c))]
    vl=[x for x in ml if x is not None]
    if not vl: return ml,[None]*len(c),[None]*len(c)
    es2=ema(vl,sg); off=len(ml)-len(vl); sl=[None]*off; si=0
    for x in ml:
        if x is None: sl.append(None)
        else: sl.append(es2[si] if si<len(es2) else None); si+=1
    hist=[ml[i]-sl[i] if ml[i] is not None and sl[i] is not None else None for i in range(len(ml))]
    return ml,sl,hist

def bb_f(c,p=20,d=2):
    u,m,l=[],[],[]
    for i in range(len(c)):
        if i<p-1: u.append(None);m.append(None);l.append(None)
        else:
            w=[x for x in c[i-p+1:i+1] if x is not None]
            if not w: u.append(None);m.append(None);l.append(None); continue
            mv=sum(w)/len(w); std=math.sqrt(sum((x-mv)**2 for x in w)/len(w))
            m.append(mv);u.append(mv+d*std);l.append(mv-d*std)
    return u,m,l

def stoch_f(H,L,C,k=14,d=3):
    sk=[]
    for i in range(len(C)):
        if i<k-1: sk.append(None)
        else:
            h=max(H[i-k+1:i+1]); l=min(L[i-k+1:i+1])
            sk.append(round(100*(C[i]-l)/(h-l),2) if h!=l else 50.0)
    vl=[x for x in sk if x is not None]
    if not vl: return sk,[None]*len(sk)
    sd=sma(vl,d); off=len(sk)-len(vl)
    return sk,[None]*off+sd

def atr_f(H,L,C,p=14):
    trs=[H[0]-L[0]]
    for i in range(1,len(C)): trs.append(max(H[i]-L[i],abs(H[i]-C[i-1]),abs(L[i]-C[i-1])))
    return [None if i<p-1 else sum(trs[i-p+1:i+1])/p for i in range(len(trs))]

def wr_f(H,L,C,p=14):
    r=[]
    for i in range(len(C)):
        if i<p-1: r.append(None)
        else:
            hh=max(H[i-p+1:i+1]); ll=min(L[i-p+1:i+1])
            r.append(round(-100*(hh-C[i])/(hh-ll),2) if hh!=ll else -50.0)
    return r

def cci_f(H,L,C,p=20):
    r=[]
    for i in range(len(C)):
        if i<p-1: r.append(None)
        else:
            tp=[(H[j]+L[j]+C[j])/3 for j in range(i-p+1,i+1)]
            m=sum(tp)/p; md=sum(abs(x-m) for x in tp)/p or 1e-9
            r.append(round((tp[-1]-m)/(0.015*md),2))
    return r

def adx_f(H,L,C,p=14):
    n=len(C)
    if n<p*2+5: return [None]*n,[None]*n,[None]*n
    try:
        trl=[];pdm=[];ndm=[]
        for i in range(1,n):
            trl.append(max(H[i]-L[i],abs(H[i]-C[i-1]),abs(L[i]-C[i-1])))
            up=H[i]-H[i-1]; dn=L[i-1]-L[i]
            pdm.append(up if up>dn and up>0 else 0.0)
            ndm.append(dn if dn>up and dn>0 else 0.0)
        def sm(v):
            if len(v)<p: return [float(sum(v))]
            r=[float(sum(v[:p]))]
            for i in range(p,len(v)): r.append(r[-1]-r[-1]/p+v[i])
            return r
        s14=sm(trl); sp=sm(pdm); sn=sm(ndm); mn=min(len(s14),len(sp),len(sn))
        pd_=[100*sp[i]/s14[i] if s14[i] else 0.0 for i in range(mn)]
        nd_=[100*sn[i]/s14[i] if s14[i] else 0.0 for i in range(mn)]
        dx=[100*abs(pd_[i]-nd_[i])/(pd_[i]+nd_[i]) if pd_[i]+nd_[i] else 0.0 for i in range(mn)]
        adxr=sm(dx)
        return [None]*(n-len(adxr))+adxr,[None]*(n-len(pd_))+pd_,[None]*(n-len(nd_))+nd_
    except: return [None]*n,[None]*n,[None]*n

def ichi_f(H,L,C):
    def mid(h,l,p,i):
        if i<p-1: return None
        return (max(h[max(0,i-p+1):i+1])+min(l[max(0,i-p+1):i+1]))/2
    tk=[mid(H,L,9,i) for i in range(len(C))]
    kj=[mid(H,L,26,i) for i in range(len(C))]
    ssa=[(tk[i]+kj[i])/2 if tk[i] is not None and kj[i] is not None else None for i in range(len(C))]
    ssb=[mid(H,L,52,i) for i in range(len(C))]
    return tk,kj,ssa,ssb

def vwap_f(candles):
    r=[]; cpv=0.0; cv=0.0
    for c in candles:
        tp=(c['h']+c['l']+c['c'])/3; v=c['v'] if c['v']>0 else 1.0
        cpv+=tp*v; cv+=v; r.append(cpv/cv)
    return r

def mfi_f(H,L,C,V,p=14):
    r=[None]*len(C)
    for i in range(p,len(C)):
        try:
            pos=neg=0.0
            for j in range(i-p+1,i+1):
                tp=(H[j]+L[j]+C[j])/3; mf=tp*V[j]
                if j>0:
                    pt=(H[j-1]+L[j-1]+C[j-1])/3
                    if tp>pt: pos+=mf
                    else: neg+=mf
            r[i]=round(100-100/(1+pos/(neg or 1e-9)),2)
        except: pass
    return r

def supertrend_f(H,L,C,atr_vals,mult=3.0):
    n=len(C); upper=[None]*n; lower=[None]*n; trend=[None]*n
    for i in range(n):
        if atr_vals[i] is None: continue
        mid=(H[i]+L[i])/2; bu=mid+mult*atr_vals[i]; bl=mid-mult*atr_vals[i]
        if i==0 or upper[i-1] is None: upper[i]=bu; lower[i]=bl; trend[i]=1; continue
        upper[i]=bu if (bu<upper[i-1] or C[i-1]>upper[i-1]) else upper[i-1]
        lower[i]=bl if (bl>lower[i-1] or C[i-1]<lower[i-1]) else lower[i-1]
        if trend[i-1]==1: trend[i]=1 if C[i]>lower[i] else -1
        else: trend[i]=-1 if C[i]<upper[i] else 1
    return trend

def swing_points(candles,lb=5):
    sh=[];sl=[]
    for i in range(lb,len(candles)-lb):
        h=candles[i]['h']; l=candles[i]['l']
        if all(h>=candles[j]['h'] for j in range(i-lb,i+lb+1) if j!=i): sh.append((i,h))
        if all(l<=candles[j]['l'] for j in range(i-lb,i+lb+1) if j!=i): sl.append((i,l))
    return sh[-4:],sl[-4:]

def order_blocks(candles):
    """ICT Order Blocks - با جزئیات بهتر و قدرت سیگنال"""
    ob_b=[]; ob_br=[]
    for i in range(2,len(candles)-1):
        c=candles[i]; n=candles[i+1]
        move=abs(n['c']-n['o'])/(n['o'] or 1)
        if c['c']<c['o'] and n['c']>n['o'] and move>0.001:
            mitigated = any(cc['l']<=c['l'] for cc in candles[i+2:])
            ob_b.append({'h':c['h'],'l':c['l'],'s':move,'idx':i,'fresh':not mitigated})
        if c['c']>c['o'] and n['c']<n['o'] and move>0.001:
            mitigated = any(cc['h']>=c['h'] for cc in candles[i+2:])
            ob_br.append({'h':c['h'],'l':c['l'],'s':move,'idx':i,'fresh':not mitigated})
    ob_b=sorted(ob_b,key=lambda x:(x['fresh'],x['s']),reverse=True)[:3]
    ob_br=sorted(ob_br,key=lambda x:(x['fresh'],x['s']),reverse=True)[:3]
    return ob_b,ob_br

def fvg_f(candles):
    """ICT Fair Value Gap - با وضعیت پر شده یا نه"""
    fb=[]; fbr=[]
    for i in range(1,len(candles)-1):
        p=candles[i-1]; n=candles[i+1]
        if n['l']>p['h']:
            filled = any(cc['l']<=p['h'] for cc in candles[i+2:])
            fb.append({'top':n['l'],'bot':p['h'],'filled':filled})
        if n['h']<p['l']:
            filled = any(cc['h']>=p['l'] for cc in candles[i+2:])
            fbr.append({'top':p['l'],'bot':n['h'],'filled':filled})
    fb=[x for x in fb if not x['filled']][-3:] or fb[-2:]
    fbr=[x for x in fbr if not x['filled']][-3:] or fbr[-2:]
    return fb,fbr

def liquidity_f(candles):
    tol=0.0005; eq_h=[]; eq_l=[]
    hs=[c['h'] for c in candles[-60:]]; ls=[c['l'] for c in candles[-60:]]
    for i in range(len(hs)):
        for j in range(i+3,len(hs)):
            if hs[i]>0 and abs(hs[i]-hs[j])/hs[i]<tol: eq_h.append((hs[i]+hs[j])/2)
    for i in range(len(ls)):
        for j in range(i+3,len(ls)):
            if ls[i]>0 and abs(ls[i]-ls[j])/ls[i]<tol: eq_l.append((ls[i]+ls[j])/2)
    return list(set([round(x,8) for x in eq_h]))[-3:], list(set([round(x,8) for x in eq_l]))[-3:]

def bos_f(candles):
    res=[]; rc=candles[-40:]
    for i in range(5,len(rc)-1):
        ph=max(c['h'] for c in rc[max(0,i-5):i]); pl=min(c['l'] for c in rc[max(0,i-5):i])
        curr=rc[i]
        if curr['c']>ph and curr['c']>curr['o']: res.append(f"BOS↑ @ {curr['c']:.5g}")
        if curr['c']<pl and curr['c']<curr['o']: res.append(f"BOS↓ @ {curr['c']:.5g}")
    return res[-3:]

def patterns_f(candles):
    p=[]
    if len(candles)<4: return p
    c2=candles[-3]; c3=candles[-2]; c4=candles[-1]
    b4=abs(c4['c']-c4['o']); r4=c4['h']-c4['l'] or 1
    uw=c4['h']-max(c4['c'],c4['o']); lw=min(c4['c'],c4['o'])-c4['l']
    if lw>b4*2 and lw>uw*2 and b4/r4>0.1: p.append("🔨 Hammer")
    if uw>b4*2 and uw>lw*2 and b4/r4>0.1: p.append("⭐ Shooting Star")
    if b4/r4<0.08: p.append("✚ Doji")
    if c4['c']>c4['o'] and c3['c']<c3['o'] and c4['c']>c3['o'] and c4['o']<c3['c']:
        p.append("🕯️ Bullish Engulfing ✅")
    if c4['c']<c4['o'] and c3['c']>c3['o'] and c4['c']<c3['o'] and c4['o']>c3['c']:
        p.append("🕯️ Bearish Engulfing ✅")
    if c2['c']<c2['o'] and abs(c3['c']-c3['o'])/(c3['h']-c3['l'] or 1)<0.3 and c4['c']>c2['c']:
        p.append("🌅 Morning Star")
    if c2['c']>c2['o'] and abs(c3['c']-c3['o'])/(c3['h']-c3['l'] or 1)<0.3 and c4['c']<c2['c']:
        p.append("🌆 Evening Star")
    if lw>r4*0.6 and b4<r4*0.25: p.append("📍 Bullish Pin Bar")
    if uw>r4*0.6 and b4<r4*0.25: p.append("📍 Bearish Pin Bar")
    if all(candles[-j]['c']>candles[-j]['o'] for j in range(1,4)): p.append("3 کندل سبز ↑")
    if all(candles[-j]['c']<candles[-j]['o'] for j in range(1,4)): p.append("3 کندل قرمز ↓")
    return p

def sr_levels(candles):
    lev=[]; tol=0.002
    hs=[c['h'] for c in candles]; ls=[c['l'] for c in candles]
    for i in range(2,len(candles)-2):
        if hs[i]>hs[i-1] and hs[i]>hs[i-2] and hs[i]>hs[i+1] and hs[i]>hs[i+2]: lev.append(('R',hs[i]))
        if ls[i]<ls[i-1] and ls[i]<ls[i-2] and ls[i]<ls[i+1] and ls[i]<ls[i+2]: lev.append(('S',ls[i]))
    mg=[]
    for t,v in lev:
        found=False
        for k,(t2,v2) in enumerate(mg):
            if v2>0 and abs(v2-v)/v2<tol: mg[k]=(t2,(v2+v)/2); found=True; break
        if not found: mg.append((t,v))
    curr=candles[-1]['c']
    return sorted([v for t,v in mg if t=='S' and v<curr],reverse=True)[:4], \
           sorted([v for t,v in mg if t=='R' and v>curr])[:4]

def fibonacci(candles,direction):
    rc=candles[-60:]; hi=max(c['h'] for c in rc); lo=min(c['l'] for c in rc); d=hi-lo
    if direction=='BUY':
        return {'38.2':round(lo+d*0.382,8),'50':round(lo+d*0.5,8),
                '61.8':round(lo+d*0.618,8),'127.2':round(hi+d*0.272,8),'161.8':round(hi+d*0.618,8)}
    return {'38.2':round(hi-d*0.382,8),'50':round(hi-d*0.5,8),'61.8':round(hi-d*0.618,8)}

def volume_a(candles):
    vs=[c['v'] for c in candles if c['v']>0]
    if len(vs)<20: return 1.0,False
    avg=sum(vs[-20:])/20; curr=vs[-1]
    return (curr/avg if avg>0 else 1.0), (curr/avg>1.5 if avg>0 else False)

# ════════════════════════════════
#  بک‌تست = فقط آمار واقعی دفترچه معاملات (get_stats در بالا)
#  شبیه‌سازی روی داده گذشته حذف شد چون آمار واقعی دقیق‌تره
# ════════════════════════════════

# ════════════════════════════════
#  Multi-TF
# ════════════════════════════════
def htf_bias(symbol,tf):
    htf_map={'1min':'1h','5min':'4h','15min':'4h','1h':'1day','4h':'1day','1day':'1day'}
    htf=htf_map.get(tf,'1h')
    try:
        cs=fetch(symbol,interval=htf,count=60)
        C=[c['c'] for c in cs]
        e21_=ema(C,21); e50_=ema(C,50); r_=rsi(C,14)
        last_e21=safe(e21_[-1],C[-1]); last_e50=safe(e50_[-1],C[-1]); last_r=safe(r_[-1],50)
        if C[-1]>last_e21>last_e50 and last_r>50: return f"📈 صعودی ({htf})"
        if C[-1]<last_e21<last_e50 and last_r<50: return f"📉 نزولی ({htf})"
        return f"➡️ خنثی ({htf})"
    except: return "❓ نامشخص"

def hourly_trend_check(symbol, signal_direction, main_tf):
    """همیشه روند تایم‌فریم ۱ ساعته رو چک میکنه و میگه آیا با سیگنال اصلی هم‌جهته یا نه.
    این مستقل از HTF Bias است که نسبت به تایم‌فریم انتخابی متغیره."""
    if main_tf=='1h': return None  # اگه خودش 1h است، تکراریه
    try:
        cs=fetch(symbol,interval='1h',count=60)
        C=[c['c'] for c in cs]
        e21_=ema(C,21); e50_=ema(C,50); r_=rsi(C,14)
        last_e21=safe(e21_[-1],C[-1]); last_e50=safe(e50_[-1],C[-1]); last_r=safe(r_[-1],50)
        if C[-1]>last_e21>last_e50 and last_r>50: h_dir="BUY"; txt="📈 صعودی"
        elif C[-1]<last_e21<last_e50 and last_r<50: h_dir="SELL"; txt="📉 نزولی"
        else: h_dir=None; txt="➡️ خنثی"
        if signal_direction=='WAIT' or h_dir is None:
            agree=None
        else:
            agree = (h_dir==signal_direction)
        return {'trend':txt,'agree':agree}
    except:
        return None

# ════════════════════════════════
#  طلا - تحلیل تخصصی
# ════════════════════════════════
def gold_special_analysis():
    """فاکتورهای خاص طلا: DXY، نرخ بهره، تورم"""
    try:
        dxy_data = fetch("DXY/USD", interval='1day', count=10)
        dxy_chg = (dxy_data[-1]['c']-dxy_data[-2]['c'])/dxy_data[-2]['c']*100
        dxy_trend = "صعودی 📈" if dxy_data[-1]['c']>dxy_data[-5]['c'] else "نزولی 📉"
    except:
        dxy_chg = None; dxy_trend = "نامشخص"

    text = "\n\n╔══════════════════════════╗\n║  🥇 تحلیل تخصصی طلا\n╚══════════════════════════╝\n"
    if dxy_chg is not None:
        corr_note = "🔴 طلا و دلار رابطه معکوس دارن" if True else ""
        text += f"  💵 شاخص دلار (DXY): {dxy_chg:+.2f}% امروز\n  📊 روند DXY (۵روزه): {dxy_trend}\n"
        if dxy_trend=="صعودی 📈":
            text += "  ⚠️ دلار قوی → معمولاً فشار نزولی روی طلا\n"
        else:
            text += "  ✅ دلار ضعیف → معمولاً فشار صعودی روی طلا\n"
    else:
        text += "  💵 داده DXY در دسترس نیست\n"

    text += ("  📌 فاکتورهای کلیدی طلا:\n"
             "    • نرخ بهره فدرال رزرو (Fed Rate)\n"
             "    • تورم آمریکا (CPI/PCE)\n"
             "    • تقاضای پناهگاه امن (ریسک ژئوپلیتیک)\n"
             "    • خرید بانک‌های مرکزی\n"
             "  💡 طلا در زمان ریسک‌گریزی و کاهش نرخ بهره معمولاً رشد میکند")
    return text

# ════════════════════════════════
#  محاسبه همه اندیکاتورها
# ════════════════════════════════
def calc_all(candles):
    C=[c['c'] for c in candles]; H=[c['h'] for c in candles]
    L=[c['l'] for c in candles]; V=[c['v'] for c in candles]
    ml,msl,mhist=macd_f(C); bu,bm,bl=bb_f(C); sk,sd=stoch_f(H,L,C)
    at=atr_f(H,L,C); wr=wr_f(H,L,C); cc=cci_f(H,L,C)
    adx_v,pdi,ndi=adx_f(H,L,C); tk,kj,ssa,ssb=ichi_f(H,L,C)
    vwap=vwap_f(candles); mfi=mfi_f(H,L,C,V); st=supertrend_f(H,L,C,at)
    sup,res=sr_levels(candles); sh,sl_s=swing_points(candles)
    ob_b,ob_br=order_blocks(candles); fvg_b,fvg_br=fvg_f(candles)
    lh,ll=liquidity_f(candles); bos=bos_f(candles); pts=patterns_f(candles)
    vr,vs_=volume_a(candles)
    return {'C':C,'H':H,'L':L,'V':V,
        'e8':ema(C,8),'e13':ema(C,13),'e21':ema(C,21),'e50':ema(C,50),'e100':ema(C,100),'e200':ema(C,200),
        'r14':rsi(C,14),'r7':rsi(C,7),'r21':rsi(C,21),
        'ml':ml,'msl':msl,'mh':mhist,'bu':bu,'bm':bm,'bl':bl,'sk':sk,'sd':sd,'at':at,'wr':wr,'cc':cc,
        'adx':adx_v,'pdi':pdi,'ndi':ndi,'tk':tk,'kj':kj,'ssa':ssa,'ssb':ssb,
        'vwap':vwap,'mfi':mfi,'st':st,'sup':sup,'res':res,'sh':sh,'sl_s':sl_s,
        'ob_bull':ob_b,'ob_bear':ob_br,'fvg_bull':fvg_b,'fvg_bear':fvg_br,
        'liq_h':lh,'liq_l':ll,'bos':bos,'patterns':pts,'vr':vr,'vs':vs_}

# ════════════════════════════════
#  موتور سیگنال
# ════════════════════════════════
def gen_signal(candles, ind, htf=""):
    i=len(candles)-1; p=i-1; pp=max(0,i-2); c=candles[i]['c']
    def g(arr,idx=None):
        if idx is None: idx=i
        if arr is None or idx>=len(arr) or idx<0: return 0.0
        v=arr[idx]; return float(v) if v is not None else 0.0

    sb=0; ss=0; rb=[]; rs=[]; ict_b=[]; ict_br=[]

    if "صعودی" in htf: sb+=4;rb.append(f"✅ HTF: {htf}")
    elif "نزولی" in htf: ss+=4;rs.append(f"✅ HTF: {htf}")

    e8=g(ind['e8']); e13=g(ind['e13']); e21=g(ind['e21'])
    e50=g(ind['e50']); e100=g(ind['e100']); e200=g(ind['e200'])
    e8p=g(ind['e8'],p); e13p=g(ind['e13'],p)
    if e8>0 and e13>0 and e21>0 and e50>0:
        if e8>e13>e21>e50>e100>e200 and e200>0: sb+=5;rb.append("EMA Bull Stack کامل 💎")
        elif e8>e13>e21>e50: sb+=3;rb.append("EMA Bull Stack")
        elif e8>e13: sb+=1;rb.append("EMA8>13")
        if e8<e13<e21<e50<e100<e200 and e200>0: ss+=5;rs.append("EMA Bear Stack کامل 💎")
        elif e8<e13<e21<e50: ss+=3;rs.append("EMA Bear Stack")
        elif e8<e13: ss+=1;rs.append("EMA8<13")
    if e8>0 and e13>0 and e8>e13 and e8p>0 and e13p>0 and e8p<=e13p: sb+=4;rb.append("🔥 Golden Cross EMA8/13")
    if e8>0 and e13>0 and e8<e13 and e8p>0 and e13p>0 and e8p>=e13p: ss+=4;rs.append("🔥 Death Cross EMA8/13")
    if e200>0 and c>e200: sb+=1;rb.append("بالای EMA200")
    if e200>0 and c<e200: ss+=1;rs.append("زیر EMA200")

    r14=g(ind['r14']); r7=g(ind['r7']); r21=g(ind['r21']); r14p=g(ind['r14'],p)
    if r14>0:
        if r14<25: sb+=4;rb.append(f"RSI اشباع فروش شدید ({r14:.0f}) 🔥")
        elif r14<35: sb+=2;rb.append(f"RSI اشباع فروش ({r14:.0f})")
        elif r14>50 and r14>r14p: sb+=1;rb.append(f"RSI صعودی ({r14:.0f})")
        if r14>75: ss+=4;rs.append(f"RSI اشباع خرید شدید ({r14:.0f}) 🔥")
        elif r14>65: ss+=2;rs.append(f"RSI اشباع خرید ({r14:.0f})")
        elif r14<50 and r14<r14p: ss+=1;rs.append(f"RSI نزولی ({r14:.0f})")
    if r7>0:
        if r7<20: sb+=2;rb.append(f"RSI7 اشباع فروش ({r7:.0f})")
        if r7>80: ss+=2;rs.append(f"RSI7 اشباع خرید ({r7:.0f})")

    ri=ind['r14']
    if len(ind['C'])>6 and ri[i] is not None and ri[max(0,i-6)] is not None:
        if ind['C'][-1]<ind['C'][-6] and ri[i]>ri[i-6]: sb+=4;rb.append("🎯 واگرایی مثبت RSI")
        if ind['C'][-1]>ind['C'][-6] and ri[i]<ri[i-6]: ss+=4;rs.append("🎯 واگرایی منفی RSI")

    mh=g(ind['mh']); mhp=g(ind['mh'],p); mhpp=g(ind['mh'],pp)
    ml_v=g(ind['ml']); msl_v=g(ind['msl'])
    if ind['mh'][i] is not None and ind['mh'][p] is not None:
        if mh>0 and mhp<=0: sb+=4;rb.append("🔥 MACD Cross Bull")
        if mh<0 and mhp>=0: ss+=4;rs.append("🔥 MACD Cross Bear")
        if mh>mhp and mhp>mhpp and mh>0: sb+=2;rb.append("MACD شتاب صعودی")
        if mh<mhp and mhp<mhpp and mh<0: ss+=2;rs.append("MACD شتاب نزولی")
    if ml_v>0 and msl_v>0: sb+=1
    if ml_v<0 and msl_v<0: ss+=1

    bu=g(ind['bu']); bl_=g(ind['bl']); bm_=g(ind['bm'])
    if bu>0 and bl_>0:
        if c<bl_: sb+=3;rb.append("🔥 زیر BB پایین")
        elif bm_>0 and c<bm_: sb+=1;rb.append("زیر میانگین BB")
        if c>bu: ss+=3;rs.append("🔥 بالای BB بالا")
        elif bm_>0 and c>bm_: ss+=1;rs.append("بالای میانگین BB")

    sk=g(ind['sk']); sd_=g(ind['sd']); skp=g(ind['sk'],p); sdp=g(ind['sd'],p)
    if sk>0:
        if sk<15 and sd_>0 and sk>sd_ and skp>0 and sdp>0 and skp<=sdp: sb+=3;rb.append("🔥 Stoch Cross اشباع فروش")
        elif sk<20: sb+=1;rb.append(f"Stoch اشباع فروش ({sk:.0f})")
        if sk>85 and sd_>0 and sk<sd_ and skp>0 and sdp>0 and skp>=sdp: ss+=3;rs.append("🔥 Stoch Cross اشباع خرید")
        elif sk>80: ss+=1;rs.append(f"Stoch اشباع خرید ({sk:.0f})")

    wr=g(ind['wr']); wrp=g(ind['wr'],p)
    if wr!=0:
        if wr<-85 and wr>wrp: sb+=2;rb.append(f"W%R اشباع فروش ({wr:.0f})")
        if wr>-15 and wr<wrp: ss+=2;rs.append(f"W%R اشباع خرید ({wr:.0f})")

    cc_=g(ind['cc']); ccp=g(ind['cc'],p)
    if cc_!=0:
        if cc_<-150: sb+=3;rb.append(f"CCI اشباع فروش شدید ({cc_:.0f})")
        elif cc_<-100: sb+=2;rb.append(f"CCI اشباع فروش ({cc_:.0f})")
        if cc_>150: ss+=3;rs.append(f"CCI اشباع خرید شدید ({cc_:.0f})")
        elif cc_>100: ss+=2;rs.append(f"CCI اشباع خرید ({cc_:.0f})")

    adx=g(ind['adx']); pdi_=g(ind['pdi']); ndi_=g(ind['ndi'])
    if adx>0:
        if adx>30 and pdi_>ndi_: sb+=3;rb.append(f"ADX روند قوی صعودی ({adx:.0f})")
        elif adx>20 and pdi_>ndi_: sb+=1;rb.append(f"ADX روند ({adx:.0f})")
        if adx>30 and ndi_>pdi_: ss+=3;rs.append(f"ADX روند قوی نزولی ({adx:.0f})")
        elif adx>20 and ndi_>pdi_: ss+=1;rs.append(f"ADX روند ({adx:.0f})")

    tk_=g(ind['tk']); kj_=g(ind['kj']); ssa_=g(ind['ssa']); ssb_=g(ind['ssb'])
    if tk_>0 and kj_>0:
        if ssa_>0 and ssb_>0:
            ct=max(ssa_,ssb_); cb=min(ssa_,ssb_)
            if c>ct: sb+=3;rb.append("☁️ بالای ابر Kumo")
            if c<cb: ss+=3;rs.append("☁️ زیر ابر Kumo")
        if tk_>kj_: sb+=1;rb.append("TK>KJ Bull")
        if tk_<kj_: ss+=1;rs.append("TK<KJ Bear")

    vwap_=ind['vwap'][-1] if ind['vwap'] else c
    if vwap_>0:
        if c>vwap_*1.001: sb+=1;rb.append("بالای VWAP")
        if c<vwap_*0.999: ss+=1;rs.append("زیر VWAP")

    mfi_=g(ind['mfi'])
    if mfi_>0:
        if mfi_<20: sb+=2;rb.append(f"MFI اشباع فروش ({mfi_:.0f})")
        if mfi_>80: ss+=2;rs.append(f"MFI اشباع خرید ({mfi_:.0f})")

    st_=ind['st'][i] if ind['st'] and ind['st'][i] is not None else 0
    if st_==1: sb+=3;rb.append("✅ Supertrend Bull")
    if st_==-1: ss+=3;rs.append("✅ Supertrend Bear")

    if ind['vs']:
        if c>candles[p]['c']: sb+=3;rb.append(f"📊 حجم انفجاری Bull ({ind['vr']:.1f}x)")
        else: ss+=3;rs.append(f"📊 حجم انفجاری Bear ({ind['vr']:.1f}x)")

    # ICT Order Blocks - نمایش بهتر با وضعیت تازگی
    for ob in ind['ob_bull']:
        if ob['l']<=c<=ob['h']*1.005:
            fresh_tag = "🆕تازه" if ob.get('fresh') else "قدیمی"
            ict_b.append(f"📦 Bullish OB ({fresh_tag}): {ob['l']:.5g}-{ob['h']:.5g}")
            sb+= 5 if ob.get('fresh') else 3
    for ob in ind['ob_bear']:
        if ob['l']*0.995<=c<=ob['h']:
            fresh_tag = "🆕تازه" if ob.get('fresh') else "قدیمی"
            ict_br.append(f"📦 Bearish OB ({fresh_tag}): {ob['l']:.5g}-{ob['h']:.5g}")
            ss+= 5 if ob.get('fresh') else 3

    # ICT FVG - فقط FVGهای پر نشده
    for fvg in ind['fvg_bull']:
        if fvg['bot']<=c<=fvg['top']:
            ict_b.append(f"⚡ Bull FVG (باز): {fvg['bot']:.5g}-{fvg['top']:.5g}"); sb+=3
    for fvg in ind['fvg_bear']:
        if fvg['bot']<=c<=fvg['top']:
            ict_br.append(f"⚡ Bear FVG (باز): {fvg['bot']:.5g}-{fvg['top']:.5g}"); ss+=3

    for liq in ind['liq_l']:
        if liq>0 and abs(c-liq)/c<0.003: ict_b.append(f"💧 Buy-Side Liquidity: {liq:.5g}"); sb+=2
    for liq in ind['liq_h']:
        if liq>0 and abs(c-liq)/c<0.003: ict_br.append(f"💧 Sell-Side Liquidity: {liq:.5g}"); ss+=2

    pa_b=[]; pa_s_=[]
    for pt in ind['patterns']:
        if any(x in pt for x in ['Bullish','Morning','Hammer','سبز','Pin Bar']): pa_b.append(pt); sb+=2
        elif any(x in pt for x in ['Bearish','Evening','Star','قرمز']): pa_s_.append(pt); ss+=2

    for sv in ind['sup']:
        if sv>0 and abs(c-sv)/c<0.005: sb+=2;rb.append(f"🎯 حمایت: {sv:.5g}")
    for rv in ind['res']:
        if rv>0 and abs(c-rv)/c<0.005: ss+=2;rs.append(f"🎯 مقاومت: {rv:.5g}")

    at=g(ind['at']) or c*0.001

    if sb>=9 and sb>ss+2:
        direction="BUY"
        sl_vals=[x[1] for x in ind['sl_s'] if x[1]<c]
        sl_base=min(sl_vals) if sl_vals else c-2.5*at
        sl=round(min(sl_base-at*0.2, c-at*1.5),8)
        risk=c-sl
        if risk<=0: risk=at*1.5; sl=round(c-risk,8)
        # سطوح واقع‌بینانه‌تر (1:1 تا 1:3.5) به‌جای اهداف خیلی دور
        tp1=round(c+risk*1.0,8); tp2=round(c+risk*1.5,8); tp3=round(c+risk*2.5,8); tp4=round(c+risk*3.5,8)
        if sb>=20: strength="💎 استثنایی"
        elif sb>=15: strength="🔥 فوق‌العاده"
        elif sb>=12: strength="💪 خیلی قوی"
        else: strength="✅ قوی"
        win_est=min(78,50+sb*1.1); reasons=rb; ict_sig=ict_b; pa_sig=pa_b
    elif ss>=9 and ss>sb+2:
        direction="SELL"
        sl_vals=[x[1] for x in ind['sh'] if x[1]>c]
        sl_base=max(sl_vals) if sl_vals else c+2.5*at
        sl=round(max(sl_base+at*0.2, c+at*1.5),8)
        risk=sl-c
        if risk<=0: risk=at*1.5; sl=round(c+risk,8)
        tp1=round(c-risk*1.0,8); tp2=round(c-risk*1.5,8); tp3=round(c-risk*2.5,8); tp4=round(c-risk*3.5,8)
        if ss>=20: strength="💎 استثنایی"
        elif ss>=15: strength="🔥 فوق‌العاده"
        elif ss>=12: strength="💪 خیلی قوی"
        else: strength="✅ قوی"
        win_est=min(78,50+ss*1.1); reasons=rs; ict_sig=ict_br; pa_sig=pa_s_
    else:
        direction="WAIT"; sl=tp1=tp2=tp3=tp4=0; risk=0
        strength="⏳ منتظر"; win_est=0
        reasons=["سیگنال کافی نیست — صبر کن"]; ict_sig=[]; pa_sig=[]

    rr=round(abs(tp2-c)/risk,2) if risk>0 and direction!="WAIT" else 0
    fib=fibonacci(candles,direction) if direction!="WAIT" else {}

    # توضیح روایی درباره چیزی که احتمالاً اتفاق میفته
    narrative = build_trade_narrative(direction, ind, candles, sb, ss) if direction!="WAIT" else ""

    return {'dir':direction,'entry':c,'sl':sl,'tp1':tp1,'tp2':tp2,'tp3':tp3,'tp4':tp4,
        'strength':strength,'win_est':win_est,'rr':rr,'risk':risk,'narrative':narrative,
        'reasons':reasons[:8],'ict_sig':ict_sig[:4],'pa_sig':pa_sig[:3],
        'bos':ind['bos'],'patterns':ind['patterns'],'fib':fib,
        'r14':r14,'r7':r7,'r21':r21,'at':at,'sk':sk,'sd':sd_,'mh':mh,'ml':ml_v,
        'bu':bu,'bl':bl_,'bm':bm_,'e8':e8,'e13':e13,'e21':e21,'e50':e50,'e200':e200,
        'wr':wr,'cc':cc_,'adx':adx,'pdi':pdi_,'ndi':ndi_,'tk':tk_,'kj':kj_,
        'vwap':vwap_,'mfi':mfi_,'st':st_,'vr':ind['vr'],'vs':ind['vs'],
        'sup':ind['sup'],'res':ind['res'],'sb':sb,'ss':ss}

def build_trade_narrative(direction, ind, candles, sb, ss):
    """توضیح می‌دهد که چه سناریویی برای این معامله محتمل‌تر است:
    حرکت مستقیم، اصلاح قبل از ادامه، یا ریسک برگشت"""
    c=candles[-1]['c']
    i=len(candles)-1
    def g(arr,idx=None):
        if idx is None: idx=i
        if arr is None or idx>=len(arr) or idx<0: return 0.0
        v=arr[idx]; return float(v) if v is not None else 0.0

    r14=g(ind['r14'])
    bb_pos = "نامشخص"
    bu=g(ind['bu']); bl_=g(ind['bl']); bm_=g(ind['bm'])
    near_fvg = False
    near_ob = False
    for fvg in (ind['fvg_bull'] if direction=='BUY' else ind['fvg_bear']):
        if fvg['bot']<=c<=fvg['top']: near_fvg=True
    for ob in (ind['ob_bull'] if direction=='BUY' else ind['ob_bear']):
        if ob['l']<=c<=ob['h']*1.01: near_ob=True

    score = sb if direction=='BUY' else ss
    opp_score = ss if direction=='BUY' else sb
    score_gap = score - opp_score

    lines=[]

    # سناریوی ۱: ورود مستقیم در محدوده Order Block / FVG تازه
    if near_ob or near_fvg:
        lines.append(
            "📍 سناریوی محتمل: قیمت داخل یک منطقه تقاضا/عرضه (Order Block یا FVG) قرار دارد. "
            "معمولاً انتظار می‌رود واکنش نسبتاً سریع از همین ناحیه رخ دهد، اما اگر این ناحیه شکسته شود "
            "(یعنی قیمت کاملاً از آن رد شود)، اعتبار سیگنال از بین می‌رود و بهتر است معامله را نگه نداری."
        )
    # سناریوی ۲: RSI در میانه — احتمال نوسان قبل از حرکت اصلی
    elif 40 < r14 < 60:
        lines.append(
            "📍 سناریوی محتمل: RSI در ناحیه میانی است، یعنی هنوز شتاب قوی شکل نگرفته. "
            "احتمال دارد قیمت قبل از حرکت اصلی به سمت تارگت، یک اصلاح کوتاه (Pullback) انجام دهد. "
            "اگر معامله را گرفتی، نزدیک Entry نوسان رو طبیعی در نظر بگیر و فقط اگر SL خورد نگران شو."
        )
    # سناریوی ۳: اشباع شدید — حرکت ممکنه سریع باشه ولی ریسک برگشت هم هست
    elif r14>70 or r14<30:
        lines.append(
            "📍 سناریوی محتمل: اندیکاتورها در ناحیه اشباع هستند، یعنی این یک معامله برگشتی (Reversal) است. "
            "حرکت‌های برگشتی می‌توانند سریع باشند ولی ریسک بیشتری هم دارند چون روند اصلی هنوز عوض نشده. "
            "حد ضرر را جدی بگیر."
        )
    else:
        lines.append(
            "📍 سناریوی محتمل: سیگنال بر اساس همسویی چند اندیکاتور و روند شکل گرفته. "
            "حرکت غالباً تدریجی و در راستای روند فعلی انتظار می‌رود، نه یک پرش ناگهانی."
        )

    if score_gap < 4:
        lines.append("⚠️ فاصله امتیاز Bull/Bear کم است؛ یعنی مخالف هم وجود دارد. این سیگنال نسبت به سیگنال‌های با فاصله امتیاز بالا، شکننده‌تر است.")
    elif score_gap >= 10:
        lines.append("✅ فاصله امتیاز Bull/Bear بالاست؛ یعنی اکثر اندیکاتورها هم‌جهت هستند — اعتماد بیشتری به این سیگنال می‌توان داشت.")

    return "\n".join(lines)

def ascii_chart(candles,sig):
    data=candles[-28:]
    mn=min(c['l'] for c in data); mx=max(c['h'] for c in data)
    rng=mx-mn if mx!=mn else 1; H=10; rows=["```"]
    for row in range(H,-1,-1):
        val=mn+(row/H)*rng; label=f"{val:.5g}".rjust(9); line=""
        for cd in data:
            nm=(cd['c']-mn)/rng*H; hn=(cd['h']-mn)/rng*H; ln=(cd['l']-mn)/rng*H
            if abs(nm-row)<0.45: line+="█" if cd['c']>=cd['o'] else "░"
            elif ln<=row<=hn: line+="│"
            else: line+=" "
        mk=""
        if sig['dir']!='WAIT' and val>0:
            if abs(val-sig['entry'])/val<0.009: mk=" ◄ENTRY"
            elif sig['sl']>0 and abs(val-sig['sl'])/val<0.009: mk=" ✕SL"
            elif sig['tp2']>0 and abs(val-sig['tp2'])/val<0.009: mk=" ✓TP2"
        rows.append(f"{label}│{line}{mk}")
    rows.append(" "*10+"└"+"─"*len(data)+"```")
    return "\n".join(rows)

def fund(symbol):
    cm={'BTC':'bitcoin','ETH':'ethereum','BNB':'binancecoin','SOL':'solana','XRP':'ripple',
        'ADA':'cardano','DOGE':'dogecoin','AVAX':'avalanche-2','LINK':'chainlink','LTC':'litecoin',
        'DOT':'polkadot','MATIC':'matic-network','SHIB':'shiba-inu','TRX':'tron','ATOM':'cosmos',
        'UNI':'uniswap','NEAR':'near','FTM':'fantom','ARB':'arbitrum','OP':'optimism',
        'INJ':'injective-protocol','SUI':'sui','APT':'aptos','PEPE':'pepe','WLD':'worldcoin-wld'}
    base=symbol.split('/')[0]; cid=cm.get(base,base.lower())
    try:
        r=requests.get(f"https://api.coingecko.com/api/v3/coins/{cid}",
            params={"localization":"false","tickers":"false"},timeout=10)
        if r.status_code!=200: return ""
        d=r.json(); md=d.get('market_data',{})
        p=md.get('current_price',{}).get('usd',0)
        c1=md.get('price_change_percentage_24h',0); c7=md.get('price_change_percentage_7d',0)
        c30=md.get('price_change_percentage_30d',0); c1y=md.get('price_change_percentage_1y',0)
        mcap=md.get('market_cap',{}).get('usd',0); vol=md.get('total_volume',{}).get('usd',0)
        rank=d.get('market_cap_rank','N/A'); sent=d.get('sentiment_votes_up_percentage',50)
        ath=md.get('ath',{}).get('usd',0); atl=md.get('atl',{}).get('usd',0)
        ath_d=((p-ath)/ath*100) if ath>0 else 0; atl_r=((p-atl)/atl*100) if atl>0 else 0
        vr=vol/mcap if mcap>0 else 0; fair=round(p*(1.2 if vr>0.1 else 0.8 if vr<0.02 else 1.0),6)
        fg=""
        try:
            fg_r=requests.get("https://api.alternative.me/fng/?limit=1",timeout=5).json()
            fgv=fg_r['data'][0]; v=int(fgv['value'])
            mood="😱ترس شدید" if v<20 else "😰ترس" if v<40 else "😐خنثی" if v<60 else "😊طمع" if v<80 else "🤑طمع شدید"
            fg=f"\n  F&G: {v} — {mood}"
        except: pass
        return (f"\n\n╔══════════════════════════╗\n║  📊 فاندامنتال {base}\n╚══════════════════════════╝\n"
                f"  🏆 رتبه: #{rank}\n  💎 مارکت‌کپ: ${mcap:,.0f}\n  📊 حجم ۲۴h: ${vol:,.0f}\n"
                f"  📈 ۲۴h:{c1:+.1f}% | ۷d:{c7:+.1f}% | ۳۰d:{c30:+.1f}% | ۱Y:{c1y:+.0f}%\n"
                f"  🔺 ATH: ${ath:,.5g} ({ath_d:.1f}% فاصله)\n  🔻 ATL: ${atl:,.5g} (+{atl_r:.0f}%)\n"
                f"  💭 سنتیمنت: {sent:.0f}% مثبت\n  💡 قیمت ذاتی تقریبی: ${fair:,.5g}{fg}")
    except: return ""

# ════════════════════════════════
#  اخبار یکپارچه (فارکس + کریپتو)
# ════════════════════════════════
def unified_news():
    """اخبار فارکس و کریپتو با هم در یک نمای واحد"""
    flags={'USD':'🇺🇸','EUR':'🇪🇺','GBP':'🇬🇧','JPY':'🇯🇵','AUD':'🇦🇺',
           'CAD':'🇨🇦','CHF':'🇨🇭','NZD':'🇳🇿','CNY':'🇨🇳'}
    text = "📰 مرکز اخبار یکپارچه\n━━━━━━━━━━━━━━━━━━━━━━\n\n"

    # بخش فارکس
    forex_found=False
    for url in ["https://nfs.faireconomy.media/ff_calendar_thisweek.json",
                "https://cdn-nfs.faireconomy.media/ff_calendar_thisweek.json"]:
        try:
            r=requests.get(url,timeout=10,headers={"User-Agent":"Mozilla/5.0"})
            if r.status_code!=200: continue
            events=r.json(); now=datetime.utcnow()
            up=[]; rc=[]
            for e in events:
                if e.get('impact','')!='High': continue
                try:
                    dt=datetime.strptime(e.get('date','')[:19],'%Y-%m-%dT%H:%M:%S')
                    diff=(dt-now).total_seconds()/3600
                    if -6<diff<0: rc.append((diff,dt,e))
                    elif 0<=diff<24: up.append((diff,dt,e))
                except: pass
            if up or rc:
                forex_found=True
                text+="💱 فارکس — رویدادهای مهم:\n"
                for diff,dt,e in sorted(up,key=lambda x:x[0])[:4]:
                    fg=flags.get(e.get('country',''),'🌍'); mins=int(diff*60)
                    tim=f"{mins}دقیقه!" if mins<60 else f"{diff:.1f}ساعت"
                    text+=f"  🔴 {fg}{e.get('country','')} {e.get('title','')} — {tim}\n"
                for diff,dt,e in sorted(rc,key=lambda x:x[0],reverse=True)[:3]:
                    fg=flags.get(e.get('country',''),'🌍'); act=e.get('actual','')
                    text+=f"  🟡 {fg}{e.get('country','')} {e.get('title','')} — واقعی:{act}\n"
                text+="\n"
            break
        except: continue
    if not forex_found:
        text+="💱 فارکس: رویداد فوری یافت نشد\n\n"

    # بخش کریپتو
    try:
        r=requests.get("https://api.coingecko.com/api/v3/news",timeout=8)
        if r.status_code==200:
            news=r.json().get('data',[])[:5]
            text+="🪙 کریپتو — آخرین اخبار:\n"
            for n in news:
                text+=f"  • {n.get('title','')[:75]}\n    [{n.get('news_site','')}]\n"
            text+="\n"
    except:
        text+="🪙 کریپتو: دریافت اخبار ممکن نشد\n\n"

    # Fear & Greed
    try:
        fg_r=requests.get("https://api.alternative.me/fng/?limit=1",timeout=5).json()
        fgv=fg_r['data'][0]; v=int(fgv['value'])
        mood="😱ترس شدید" if v<20 else "😰ترس" if v<40 else "😐خنثی" if v<60 else "😊طمع" if v<80 else "🤑طمع شدید"
        text+=f"📊 احساسات کلی بازار: {v} — {mood}\n"
    except: pass

    text+=f"\n⏱ سشن فعلی: {get_session()} | کیفیت: {session_quality()}"
    return text

def global_market():
    try:
        r=requests.get("https://api.coingecko.com/api/v3/global",timeout=8)
        d=r.json().get('data',{})
        btc=d.get('market_cap_percentage',{}).get('btc',0)
        eth=d.get('market_cap_percentage',{}).get('eth',0)
        total=d.get('total_market_cap',{}).get('usd',0)
        chg=d.get('market_cap_change_percentage_24h_usd',0)
        active=d.get('active_cryptocurrencies',0)
        fg=""
        try:
            fg_r=requests.get("https://api.alternative.me/fng/?limit=1",timeout=5).json()
            fgv=fg_r['data'][0]; v=int(fgv['value'])
            mood="😱ترس شدید" if v<20 else "😰ترس" if v<40 else "😐خنثی" if v<60 else "😊طمع" if v<80 else "🤑طمع شدید"
            fg=f"\n  F&G: {v} — {mood}"
        except: pass
        return (f"🌍 وضعیت کل بازار\n━━━━━━━━━━━━━━━━━━━━━━\n"
                f"  💰 مارکت کپ: ${total:,.0f}\n  {'📈' if chg>0 else '📉'} ۲۴h: {chg:+.2f}%\n"
                f"  ₿ BTC: {btc:.1f}% | Ξ ETH: {eth:.1f}%\n  🔢 ارزهای فعال: {active:,}{fg}\n\n"
                f"  ⏱ سشن: {get_session()}\n  🎯 کیفیت: {session_quality()}")
    except: return "❌ خطا"

def build_msg(symbol,sig,candles,ind,fundamental,tf_name,htf_str="",hourly=None,symbol_stats=None):
    c=candles[-1]['c']; prev=candles[-2]['c']; chg=(c-prev)/prev*100
    e8,e13,e21,e50,e200=sig['e8'],sig['e13'],sig['e21'],sig['e50'],sig['e200']
    if e8>0 and e13>0 and e21>0 and e50>0 and e200>0 and e8>e13>e21>e50>e200: trend="📈 Bull Stack کامل"
    elif e8>0 and e13>0 and e21>0 and e8>e13>e21: trend="📈 صعودی"
    elif e8>0 and e13>0 and e8>e13: trend="↗️ احتمالاً صعودی"
    elif e8>0 and e13>0 and e21>0 and e50>0 and e200>0 and e8<e13<e21<e50<e200: trend="📉 Bear Stack کامل"
    elif e8>0 and e13>0 and e21>0 and e8<e13<e21: trend="📉 نزولی"
    elif e8>0 and e13>0 and e8<e13: trend="↘️ احتمالاً نزولی"
    else: trend="➡️ خنثی"

    r14=sig['r14']
    if r14>75: rs="اشباع خرید شدید 🔴"
    elif r14>65: rs="اشباع خرید ⚠️"
    elif r14<25: rs="اشباع فروش شدید 🟢"
    elif r14<35: rs="اشباع فروش ⚠️"
    elif r14>55: rs="قوی"
    elif r14<45: rs="ضعیف"
    else: rs="خنثی"

    d=sig['dir']
    if d=='BUY': dt="🟢 BUY / LONG 📈"
    elif d=='SELL': dt="🔴 SELL / SHORT 📉"
    else: dt="🟡 WAIT — صبر کن"

    reasons="\n".join(f"  ▸ {r}" for r in sig['reasons'][:7])
    ict="\n".join(f"  ◆ {s}" for s in sig['ict_sig'][:4]) or "  — هیچ منطقه ICT فعالی نزدیک قیمت نیست"
    pa="\n".join(f"  ◇ {s}" for s in sig['patterns'][:3]) or "  — الگوی کندلی خاصی نیست"
    bos="\n".join(f"  → {s}" for s in sig['bos'][:2]) or "  — BOS شناسایی نشد"
    sup_t=" | ".join(f"{x:.5g}" for x in sig['sup'][:3]) or "N/A"
    res_t=" | ".join(f"{x:.5g}" for x in sig['res'][:3]) or "N/A"
    vt=f"{'📊 حجم انفجاری! ' if sig['vs'] else ''}{sig['vr']:.1f}x میانگین"
    chart=ascii_chart(candles,sig)
    fib=sig.get('fib',{})

    msg=f"""╔══════════════════════════════╗
║  🤖 TITAN ULTIMATE v5.0     ║
╠══════════════════════════════╣
║  {symbol:<14}  ⏱ {tf_name}
╚══════════════════════════════╝
💰 قیمت:  {c:.6g}
📊 تغییر: {chg:+.2f}%
🔁 روند:  {trend}
🌍 HTF:   {htf_str}
⏱ سشن:   {get_session()}
🎯 کیفیت: {session_quality()}
📦 حجم:   {vt}

{chart}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  🎯 سیگنال:  {dt}
  💪 قدرت:   {sig['strength']}
  🔢 امتیاز: Bull {sig['sb']} | Bear {sig['ss']}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"""

    if hourly is not None and d!='WAIT':
        if hourly['agree'] is True:
            msg+=f"\n  🕐 تایم‌فریم ۱ساعته: {hourly['trend']} — ✅ هم‌جهت با سیگنال"
        elif hourly['agree'] is False:
            msg+=f"\n  🕐 تایم‌فریم ۱ساعته: {hourly['trend']} — ⚠️ خلاف جهت سیگنال (احتیاط کن)"
        else:
            msg+=f"\n  🕐 تایم‌فریم ۱ساعته: {hourly['trend']} — جهت واضحی ندارد"

    if d!='WAIT':
        rp=abs(sig['risk']/c*100) if c>0 else 0
        msg+=f"""
  📍 ورود:    {sig['entry']:.6g}
  🛑 SL:     {sig['sl']:.6g}  (-{rp:.2f}%)
  ─────────────────────
  🎯 TP1:    {sig['tp1']:.6g}  (R:R 1:1.0)
  🎯 TP2:    {sig['tp2']:.6g}  (R:R 1:1.5) ★
  🎯 TP3:    {sig['tp3']:.6g}  (R:R 1:2.5)
  🎯 TP4:    {sig['tp4']:.6g}  (R:R 1:3.5)
  ─────────────────────
  ⚖️  R:R اصلی: 1:{sig['rr']}
  🎰 Win Rate تخمینی (نظری): ~{sig['win_est']:.0f}%
  ⚠️ این عدد فقط بر اساس امتیاز اندیکاتورهاست، نه آمار واقعی."""

        if symbol_stats:
            msg+=f"""
  ─────────────────────
  📓 عملکرد واقعی تو روی {symbol}:
    از {symbol_stats['total']} معامله ثبت‌شده قبلی
    ✅ موفق: {symbol_stats['wins']} | نرخ واقعی: {symbol_stats['wr']:.0f}%"""
        else:
            msg+=f"""
  ─────────────────────
  📓 هنوز برای {symbol} داده کافی در دفترچه معاملاتت نیست (حداقل ۳ معامله لازمه)
    برای آمار دقیق، سیگنال‌ها رو ثبت کن و بعداً اینجا میبینی."""

        if sig.get('narrative'):
            msg+=f"\n  ─────────────────────\n  📖 توضیح سناریو:\n  {sig['narrative']}"

        msg+=f"""
  ─────────────────────
  💡 مدیریت:
    ✦ TP1 → SL به Entry
    ✦ TP2 → ۵۰٪ سود بگیر
    ✦ TP3 → ۲۵٪ دیگه ببند
    ✦ TP4 → بقیه رها کن"""
        if fib:
            msg+="\n  ─────────────────────\n  📐 Fibonacci:"
            for k,v in fib.items(): msg+=f"\n    {k}%: {v:.5g}"

    msg+=f"""

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  📐 اندیکاتورها:
  RSI14: {r14:.0f} — {rs}
  RSI7: {sig['r7']:.0f} | RSI21: {sig['r21']:.0f}
  MACD: {'✅Bull↑' if sig['mh']>0 else '❌Bear↓'}
  Stoch: K={sig['sk']:.0f} D={sig['sd']:.0f}
  W%R:{sig['wr']:.0f} | CCI:{sig['cc']:.0f} | MFI:{sig['mfi']:.0f}
  ADX:{sig['adx']:.0f} +DI:{sig['pdi']:.0f} -DI:{sig['ndi']:.0f}
  Ichi: TK={sig['tk']:.5g} KJ={sig['kj']:.5g}
  ST: {'✅Bull' if sig['st']==1 else '❌Bear' if sig['st']==-1 else '—'}
  VWAP: {sig['vwap']:.6g}
  EMA: 8={e8:.4g} | 13={e13:.4g} | 21={e21:.4g}
       50={e50:.4g} | 200={e200:.4g}
  BB: ↑{sig['bu']:.5g} ↓{sig['bl']:.5g}
  ATR: {sig['at']:.6g}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  📌 S/R:
  حمایت:  {sup_t}
  مقاومت: {res_t}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  🏛️ Smart Money (ICT):
{ict}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  🕯️ Price Action:
{pa}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  🔍 BOS/CHoCH:
{bos}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  ✅ دلایل:
{reasons}
{fundamental}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
⚠️  فقط آموزشی | ریسک مدیریت کن
🕐 {datetime.now().strftime('%Y-%m-%d %H:%M')}"""
    return msg

async def auto_scanner(app):
    global scanner_active, scanner_tf, last_signals
    while scanner_active:
        try:
            syms=list(SCAN_LIST)+list(WATCHLIST)
            for sym in syms:
                if not scanner_active: break
                try:
                    cs=fetch(sym,interval=scanner_tf,count=150)
                    if len(cs)<50: continue
                    ind_=calc_all(cs)
                    sig=gen_signal(cs,ind_)
                    score=max(sig['sb'],sig['ss'])
                    key=f"{sym}_{sig['dir']}"
                    if sig['dir']!='WAIT' and score>=12 and last_signals.get(key,0)<score-2:
                        last_signals[key]=score
                        d=sig['dir']; e="🟢" if d=='BUY' else "🔴"
                        msg=(f"🚨 سیگنال قوی!\n\n{e} {sym} — {d}\n"
                             f"💪 {sig['strength']}\n🔢 امتیاز: {score}\n"
                             f"📍 ورود: {sig['entry']:.6g}\n🛑 SL: {sig['sl']:.6g}\n"
                             f"🎯 TP2: {sig['tp2']:.6g}\n⚖️ R:R: 1:{sig['rr']}\n"
                             f"🎰 Win: ~{sig['win_est']:.0f}%\n\n"
                             f"برای تحلیل کامل بنویس:\n{sym.replace('/','')}")
                        await app.bot.send_message(chat_id=ALLOWED_ID,text=msg)
                        await asyncio.sleep(3)
                except: pass
                await asyncio.sleep(4)
            await check_open_trades(app)
        except: pass
        await asyncio.sleep(SCAN_INTERVAL)

def main_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 تحلیل کامل",callback_data='analyze'),
         InlineKeyboardButton("🌍 وضعیت بازار",callback_data='market')],
        [InlineKeyboardButton("📰 مرکز اخبار",callback_data='news')],
        [InlineKeyboardButton("🤖 اسکنر خودکار",callback_data='scanner'),
         InlineKeyboardButton("👁 واچ‌لیست",callback_data='watchlist')],
        [InlineKeyboardButton("📓 دفترچه معاملات",callback_data='journal'),
         InlineKeyboardButton("🏆 برترین کریپتو",callback_data='top')],
        [InlineKeyboardButton("📋 لیست ارزها",callback_data='list'),
         InlineKeyboardButton("❓ راهنما",callback_data='help')],
    ])

async def cmd_start(update,context):
    if not auth(update): return
    await update.message.reply_text(
        "╔══════════════════════════════╗\n"
        "║  🤖 TITAN ULTIMATE v5.0     ║\n"
        "║  +Trade Journal +GoldPro    ║\n"
        "╚══════════════════════════════╝\n\n"
        f"⏱ سشن: {get_session()}\n🎯 کیفیت: {session_quality()}\n\nاز منوی زیر انتخاب کن:",
        reply_markup=main_kb())

async def do_analysis(msg_obj, symbol, tf, context=None):
    tfm={'1min':'۱ دقیقه','5min':'۵ دقیقه','15min':'۱۵ دقیقه',
         '1h':'۱ ساعت','4h':'۴ ساعت','1day':'روزانه'}
    tf_name=tfm.get(tf,tf)
    wait=await msg_obj.reply_text(f"⏳ تحلیل {symbol} ({tf_name})...")
    try:
        cs=fetch(symbol,interval=tf,count=200)
        if len(cs)<50: raise ValueError("داده کافی نیست")
        htf_str=htf_bias(symbol,tf)
        ind_=calc_all(cs)
        sig=gen_signal(cs,ind_,htf_str)
        hourly=hourly_trend_check(symbol,sig['dir'],tf)
        # آمار واقعی از دفترچه معاملات (فقط برای همین نماد، اگر داده‌ای هست)
        all_stats=get_stats()
        symbol_trades=[t for t in load_trades() if t['symbol']==symbol and t['status']!='OPEN']
        symbol_stats=None
        if len(symbol_trades)>=3:
            wins=len([t for t in symbol_trades if str(t['status']).startswith('TP')])
            symbol_stats={'total':len(symbol_trades),'wins':wins,
                          'wr':wins/len(symbol_trades)*100}
        crypto_l=['BTC','ETH','BNB','SOL','XRP','ADA','DOGE','AVAX','LINK','LTC',
                  'DOT','MATIC','SHIB','TRX','ATOM','UNI','NEAR','FTM','ARB','OP',
                  'INJ','SUI','APT','PEPE','WLD','FLOKI']
        base=symbol.split('/')[0]
        f_=fund(symbol) if base in crypto_l else ""
        if base in ('XAU','GOLD'): f_ += gold_special_analysis()
        text=build_msg(symbol,sig,cs,ind_,f_,tf_name,htf_str,hourly,symbol_stats)
        await wait.delete()
        sent_msg = await msg_obj.reply_text(text,parse_mode='Markdown')
        if sig['dir']!='WAIT' and context is not None:
            session_now=get_session_for_trade()
            kb=InlineKeyboardMarkup([[InlineKeyboardButton(
                "📝 این معامله رو ثبت کن",
                callback_data=f"log_{symbol}_{sig['dir']}_{sig['entry']}_{sig['sl']}_{sig['tp1']}_{sig['tp2']}_{sig['tp3']}_{sig['tp4']}_{tf}_{session_now}"
            )]])
            await msg_obj.reply_text("میخوای این سیگنال رو در دفترچه معاملات ثبت کنی تا بعداً نتیجه‌اش رو پیگیری کنی؟",reply_markup=kb)
    except Exception as e:
        await wait.edit_text(f"❌ خطا: {e}")

async def callback_handler(update,context):
    global scanner_active,scanner_tf,last_signals
    q=update.callback_query; await q.answer()
    if not auth(update): return
    data=q.data

    if data=='analyze':
        await q.message.reply_text("📊 اسم ارز بنویس:\nBTC | EURUSD | GOLD | NAS100")
        context.user_data['w']='analyze'
    elif data=='market':
        w=await q.message.reply_text("⏳..."); await w.delete()
        await q.message.reply_text(global_market())
    elif data=='news':
        w=await q.message.reply_text("⏳ دریافت اخبار یکپارچه...")
        t=unified_news(); await w.delete(); await q.message.reply_text(t[:4096])
    elif data=='scanner':
        kb=InlineKeyboardMarkup([
            [InlineKeyboardButton("▶ 5min",callback_data='sc_5min'),
             InlineKeyboardButton("▶ 15min",callback_data='sc_15min'),
             InlineKeyboardButton("▶ 1h",callback_data='sc_1h')],
            [InlineKeyboardButton("⏹ توقف",callback_data='sc_stop'),
             InlineKeyboardButton("📊 وضعیت",callback_data='sc_status')],
        ])
        await q.message.reply_text(
            f"🤖 اسکنر خودکار\nوضعیت: {'🟢 فعال' if scanner_active else '🔴 غیرفعال'}\n"
            f"TF: {scanner_tf} | ارزها: {len(SCAN_LIST)+len(WATCHLIST)}\n\n"
            "سیگنال قوی → پیام فوری!\nهمچنین معاملات باز رو خودکار چک میکنه.",reply_markup=kb)
    elif data.startswith('sc_'):
        tf=data.replace('sc_','')
        if tf=='stop': scanner_active=False; await q.message.reply_text("⏹ متوقف شد")
        elif tf=='status':
            stats=get_stats()
            await q.message.reply_text(
                f"📊 اسکنر: {'🟢' if scanner_active else '🔴'}\n"
                f"TF: {scanner_tf}\nارزها: {len(SCAN_LIST)+len(WATCHLIST)}\n"
                f"واچ‌لیست: {', '.join(WATCHLIST) if WATCHLIST else 'خالی'}\n\n"
                f"📓 معاملات باز: {stats['open']}")
        else:
            scanner_tf=tf; scanner_active=True; last_signals={}
            asyncio.create_task(auto_scanner(context.application))
            await q.message.reply_text(f"✅ اسکنر شروع شد!\nTF: {tf} | هر {SCAN_INTERVAL//60}دقیقه")
    elif data=='watchlist':
        kb=InlineKeyboardMarkup([
            [InlineKeyboardButton("➕ اضافه",callback_data='wa'),
             InlineKeyboardButton("➖ حذف",callback_data='wr_'),
             InlineKeyboardButton("📋 لیست",callback_data='ws')],
        ])
        await q.message.reply_text("👁 واچ‌لیست:",reply_markup=kb)
    elif data=='wa':
        await q.message.reply_text("➕ اسم ارز:"); context.user_data['w']='wa'
    elif data=='wr_':
        await q.message.reply_text("➖ اسم ارز:"); context.user_data['w']='wr'
    elif data=='ws':
        await q.message.reply_text(f"👁 واچ‌لیست:\n{chr(10).join(WATCHLIST) if WATCHLIST else 'خالی'}")
    elif data=='journal':
        stats=get_stats()
        trades=load_trades()
        open_trades=[t for t in trades if t['status']=='OPEN'][-5:]
        if not stats['has_data']:
            text=(f"📓 دفترچه معاملات\n━━━━━━━━━━━━━━━━━━━━━━\n\n"
                  f"📊 کل معاملات ثبت‌شده: {stats['total']}\n"
                  f"📂 باز: {stats['open']}\n\n"
                  f"⏳ هنوز هیچ معامله‌ای بسته نشده. وقتی چند معامله ثبت کنی و به TP/SL برسن،\n"
                  f"آمار کامل و دقیق اینجا نمایش داده میشه.")
        else:
            text=(f"📓 دفترچه معاملات\n━━━━━━━━━━━━━━━━━━━━━━\n\n"
                  f"📊 آمار کلی:\n"
                  f"  کل معاملات ثبت‌شده: {stats['total']}\n"
                  f"  باز: {stats['open']} | بسته: {stats['closed']}\n\n"
                  f"🎯 تفکیک نتایج:\n"
                  f"  ✅ TP1: {stats['tp1']}\n"
                  f"  ✅ TP2: {stats['tp2']}\n"
                  f"  ✅ TP3: {stats['tp3']}\n"
                  f"  ✅ TP4: {stats['tp4']}\n"
                  f"  ❌ SL:  {stats['sl']}\n\n"
                  f"🏆 نرخ موفقیت کلی (Win Rate): {stats['wr']:.1f}%\n\n"
                  f"🔥 بیشترین برد پشت‌سرهم: {stats['max_win_streak']}\n"
                  f"💔 بیشترین باخت پشت‌سرهم: {stats['max_loss_streak']}\n"
                  f"⏱ میانگین مدت معامله: {stats['avg_duration_hours']:.1f} ساعت\n\n"
                  f"🌟 بهترین سشن برای تو: {stats['best_session']}\n"
                  f"⚠️ ضعیف‌ترین سشن برای تو: {stats['worst_session']}\n")
        if open_trades:
            text+="\n📂 معاملات باز اخیر:\n"
            for t in open_trades:
                text+=f"  #{t['id']} {t['symbol']} {t['direction']} — ورود:{t['entry']:.5g}\n"
        await q.message.reply_text(text)
    elif data.startswith('log_'):
        parts=data.split('_')
        symbol=parts[1]; direction=parts[2]
        entry=float(parts[3]); sl=float(parts[4])
        tp1=float(parts[5]); tp2=float(parts[6]); tp3=float(parts[7]); tp4=float(parts[8])
        tf=parts[9]; session=parts[10] if len(parts)>10 else get_session_for_trade()
        tid=log_trade(symbol,direction,entry,sl,tp1,tp2,tp3,tp4,tf,"",session)
        await q.message.reply_text(f"✅ معامله #{tid} ثبت شد!\nربات خودش رصد میکنه و وقتی به TP یا SL رسید بهت خبر میده.")
    elif data=='top':
        w=await q.message.reply_text("⏳...")
        try:
            r=requests.get("https://api.coingecko.com/api/v3/coins/markets",
                params={"vs_currency":"usd","order":"market_cap_desc","per_page":20,"page":1},timeout=10)
            coins=r.json(); text="🏆 ۲۰ ارز برتر:\n━━━━━━━━━━━━━━━━━\n"
            for idx,c in enumerate(coins,1):
                e="📈" if c['price_change_percentage_24h']>0 else "📉"
                text+=f"{idx:2}. {c['symbol'].upper():6} ${c['current_price']:>12,.5g} {e}{c['price_change_percentage_24h']:+.1f}%\n"
            await w.delete(); await q.message.reply_text(f"```\n{text}```",parse_mode='Markdown')
        except Exception as e: await w.edit_text(f"❌ {e}")
    elif data=='list':
        await q.message.reply_text(
            "📋 ارزهای پشتیبانی:\n\n"
            "🔸 کریپتو:\nBTC ETH BNB SOL XRP ADA DOGE AVAX LINK LTC DOT MATIC SHIB TRX ATOM UNI NEAR FTM ARB OP INJ SUI APT PEPE WLD FLOKI\n\n"
            "🔸 فارکس:\nEURUSD GBPUSD USDJPY AUDUSD USDCAD USDCHF NZDUSD EURGBP EURJPY GBPJPY EURCAD GBPCAD AUDCAD AUDCHF AUDJPY CHFJPY EURNZD GBPAUD GBPNZD NZDJPY\n\n"
            "🔸 کالا: GOLD SILVER OIL BRENT (طلا با تحلیل تخصصی DXY)\n🔸 شاخص: NAS100 SP500 DOW DAX")
    elif data=='help':
        await q.message.reply_text(
            "❓ راهنما:\n\n۱. تحلیل کامل → اسم ارز → TF\n۲. بعد از سیگنال میتونی ثبتش کنی\n"
            "۳. از 'دفترچه معاملات' آمار واقعی میبینی\n\n"
            "TF پیشنهادی:\n• اسکلپ: 1m/5m\n• سوئینگ: 15m/1h\n• میان‌مدت: 4h/1d\n\n"
            "اندیکاتورها (12تا):\nEMA Stack, RSI+Div, MACD, BB\nStoch, W%R, CCI, ADX, Ichimoku\nVWAP, MFI, Supertrend\n\n"
            "ICT: OB(تازه/قدیمی), FVG(باز/پر), Liquidity, BOS\n"
            "PA: Engulfing, PinBar, Star...\nFib: 38.2/50/61.8/127/161.8\nMTF: HTF Bias\n\n"
            "🕐 چک تایم‌فریم ۱ساعته:\nهمیشه میگه آیا روند ۱h با سیگنال شما هم‌جهته یا نه\n\n"
            "📓 دفترچه معاملات (v5):\n"
            "ثبت سیگنال → رصد خودکار TP1/2/3/4 یا SL\n"
            "آمار واقعی: تعداد هر TP، SL، بیشترین برد/باخت پشت سر هم،\n"
            "میانگین مدت معامله، بهترین/بدترین سشن — همه از معاملات واقعی خودت\n"
            "⚠️ هرچه بیشتر ثبت کنی، آمار دقیق‌تر میشه\n\n"
            "📖 توضیح سناریو: هر سیگنال یک توضیح کوتاه دارد که می‌گوید "
            "آیا اصلاح قبل از حرکت محتمل‌تره یا حرکت مستقیم\n\n"
            "📰 اخبار یکپارچه: فارکس+کریپتو با هم\n🥇 طلا: تحلیل تخصصی DXY")
    elif data.startswith('tf_'):
        parts=data.split('_',2); sym=parts[1]; tf=parts[2]
        await do_analysis(q.message,sym,tf,context)

async def handle_text(update,context):
    if not auth(update): return
    w=context.user_data.get('w'); txt=update.message.text.strip()
    if not w: return
    if w=='analyze':
        context.user_data['w']=None; sym=resolve(txt)
        kb=InlineKeyboardMarkup([
            [InlineKeyboardButton("⚡ ۱ دقیقه",callback_data=f"tf_{sym}_1min"),
             InlineKeyboardButton("🔥 ۵ دقیقه",callback_data=f"tf_{sym}_5min")],
            [InlineKeyboardButton("📊 ۱۵ دقیقه",callback_data=f"tf_{sym}_15min"),
             InlineKeyboardButton("📈 ۱ ساعت",callback_data=f"tf_{sym}_1h")],
            [InlineKeyboardButton("🌙 ۴ ساعت",callback_data=f"tf_{sym}_4h"),
             InlineKeyboardButton("📅 روزانه",callback_data=f"tf_{sym}_1day")],
        ])
        await update.message.reply_text(f"✅ {sym}\n⏱ تایم‌فریم:",reply_markup=kb)
    elif w=='wa':
        context.user_data['w']=None; sym=resolve(txt); WATCHLIST.add(sym)
        await update.message.reply_text(f"✅ {sym} اضافه شد")
    elif w=='wr':
        context.user_data['w']=None; sym=resolve(txt)
        if sym in WATCHLIST: WATCHLIST.remove(sym); await update.message.reply_text(f"✅ حذف شد")
        else: await update.message.reply_text(f"❌ در لیست نیست")

def main():
    app=Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler('start',cmd_start))
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND,handle_text))
    print("╔══════════════════════════════╗")
    print("║  🤖 TITAN ULTIMATE v5.0     ║")
    print("║  Journal+News+Gold Ready! ✅ ║")
    print("╚══════════════════════════════╝")
    app.run_polling(drop_pending_updates=True)

if __name__=='__main__':
    main()
