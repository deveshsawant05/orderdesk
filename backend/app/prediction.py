import math
from datetime import timedelta
import numpy as np
from sqlalchemy import select, func
from .models import PredictionModel, TrainingSample, Order, OrderItem, now

FEATURES=['pending_orders','preparing_orders','queued_quantities','order_quantity','max_item_prep','recent_completion_minutes']
MODEL_ID='synthetic-ols-v1'

def train_if_missing(db):
    if db.get(PredictionModel,MODEL_ID):
        return
    rng=np.random.default_rng(2026)
    for i in range(600):
        if db.get(TrainingSample,i+1):
            continue
        f=[int(rng.integers(0,16)),int(rng.integers(0,10)),int(rng.integers(0,70)),int(rng.integers(1,15)),int(rng.integers(8,40)),float(rng.uniform(20,65))]
        y=5+0.9*f[0]+1.2*f[1]+0.13*f[2]+0.8*f[3]+0.65*f[4]+0.12*f[5]+float(rng.normal(0,3))
        db.add(TrainingSample(id=i+1,features=f,duration=max(5,y)))
    db.flush()
    rows=list(db.scalars(select(TrainingSample).order_by(TrainingSample.id)))
    X=np.array([[1]+r.features for r in rows]); y=np.array([r.duration for r in rows])
    coef=np.linalg.lstsq(X[:480],y[:480],rcond=None)[0]
    mae=float(np.mean(np.abs(X[480:]@coef-y[480:])))
    db.add(PredictionModel(id=MODEL_ID,coefficients=coef.tolist(),feature_names=FEATURES,metrics={'heldout_mae_minutes':round(mae,3),'train_rows':480,'test_rows':120,'synthetic':True,'seed':2026}))

def predict(db,outlet,lines):
    active=list(db.scalars(select(Order).where(Order.outlet_id==outlet.id,Order.snapshot.is_(False),Order.placed_at>=now()-timedelta(hours=12),Order.status.in_(['new','preparing']))))
    quantities=db.scalar(select(func.coalesce(func.sum(OrderItem.quantity),0)).where(OrderItem.order_id.in_([o.id for o in active]))) or 0
    recent=list(db.scalars(select(Order).where(Order.outlet_id==outlet.id,Order.snapshot.is_(False),Order.completed_at.is_not(None),Order.placed_at>now()-timedelta(days=7)).order_by(Order.completed_at.desc()).limit(20)))
    durations=[(o.completed_at-o.placed_at).total_seconds()/60 for o in recent]
    f=[sum(o.status=='new' for o in active),sum(o.status=='preparing' for o in active),int(quantities),sum(l['quantity'] for l in lines),max(l['prep_minutes'] for l in lines),sum(durations)/len(durations) if durations else float(outlet.minimum_minutes)]
    model=db.get(PredictionModel,MODEL_ID)
    source=MODEL_ID
    try:
        if not model:
            raise ValueError('missing model')
        raw=float(np.dot([1]+f,model.coefficients))
        if not math.isfinite(raw) or raw<=0:
            raise ValueError('invalid model output')
        predicted=math.ceil(raw)
    except (ValueError,TypeError):
        predicted=math.ceil(f[4]+f[0]*2+f[1]*2+f[2]*0.2+f[3])
        source='deterministic-fallback'
    return {'predicted_minutes':predicted,'minimum_minutes':outlet.minimum_minutes,'promised_minutes':max(predicted,outlet.minimum_minutes),'source':source,'features':dict(zip(FEATURES,f))}
