from pathlib import Path
import sys, warnings
import numpy as np, pandas as pd
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler,OneHotEncoder
from sklearn.compose import ColumnTransformer
from sklearn.pipeline import Pipeline
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split,GridSearchCV
from sklearn.metrics import accuracy_score,precision_score,recall_score,f1_score,confusion_matrix,silhouette_score
from sklearn.decomposition import PCA
import joblib
sys.path.insert(0,str(Path(__file__).resolve().parent))
from common import ROOT,RAW,CLEAN,OUT,connect

def run():
    with connect() as con:
        customers=pd.read_sql("select * from customers",con)
        orders=pd.read_sql("select * from orders",con)
        products=pd.read_sql("select product_id,category from products",con)
    orders["order_date"]=pd.to_datetime(orders["order_date"])
    completed=orders[orders.status.eq("completed")].copy()
    snapshot=pd.Timestamp("2025-10-01")
    rfm=completed.groupby("customer_id").agg(
        last_order=("order_date","max"),frequency=("order_id","nunique"),monetary=("amount","sum")).reset_index()
    rfm["recency"]=(snapshot-rfm["last_order"]).dt.days.clip(lower=0)
    rfm=rfm[["customer_id","recency","frequency","monetary"]]
    scaler=StandardScaler()
    X=scaler.fit_transform(rfm[["recency","frequency","monetary"]])
    diagnostics=[]
    for k in range(2,9):
        candidate=KMeans(n_clusters=k,n_init=10,random_state=42)
        labels=candidate.fit_predict(X)
        diagnostics.append({"k":k,"inertia":float(candidate.inertia_),
                            "silhouette":float(silhouette_score(X,labels))})
    pd.DataFrame(diagnostics).to_csv(OUT/"kmeans_diagnostics.csv",index=False)
    km=KMeans(n_clusters=4,n_init=10,random_state=42)
    rfm["segment_id"]=km.fit_predict(X)
    profiles=rfm.groupby("segment_id").agg(size=("customer_id","size"),mean_recency=("recency","mean"),mean_frequency=("frequency","mean"),mean_monetary=("monetary","mean")).reset_index()
    order=profiles.sort_values("mean_monetary").segment_id.tolist()
    names={sid:("At Risk" if i==0 else "Regular" if i==1 else "Loyal" if i==2 else "Premium") for i,sid in enumerate(order)}
    rfm["segment_name"]=rfm["segment_id"].map(names)
    rfm["is_premium"]=(rfm.segment_name=="Premium").astype(int)
    rfm.to_csv(OUT/"customer_segments.csv",index=False)
    pca=PCA(n_components=2,random_state=42).fit(X)
    print("RFM customers:",len(rfm),"PCA explained variance:",np.round(pca.explained_variance_ratio_,3).tolist())
    print("Segment profiles:\n",profiles.to_string(index=False))

    # Leakage-safe label/features: all feature aggregates strictly before 2025-09-01.
    cutoff=pd.Timestamp("2025-09-01")
    pre=orders[orders.order_date<cutoff].copy()
    cohort=pre.loc[pre.status.eq("completed"),"customer_id"].drop_duplicates()
    future=completed[(completed.order_date>=cutoff)&(completed.order_date<pd.Timestamp("2025-10-01"))]
    lapsed=set(cohort)-set(future.customer_id)
    print("Lapse cohort:",len(cohort),"lapsed:",len(lapsed),"rate:",round(len(lapsed)/len(cohort),4) if len(cohort)>0 else 0)
    feat=pre.groupby("customer_id").agg(
        frequency=("order_id","nunique"),monetary=("amount","sum"),
        avg_discount=("discount_pct","mean"),
        cancellation_rate=("status",lambda x:(x=="cancelled").mean()),
        avg_delivery=("delivery_minutes","mean"),last_order=("order_date","max")).reset_index()
    feat["recency"]=(cutoff-feat["last_order"]).dt.days
    feat["lapsed"]=feat.customer_id.isin(lapsed).astype(int)
    feat=feat.merge(customers[["customer_id","city","gender","age","signup_date"]],on="customer_id",how="left")
    feat["tenure_days"]=(cutoff-pd.to_datetime(feat["signup_date"])).dt.days
    cat_source=pre.merge(products[["product_id","category"]],on="product_id",how="left",suffixes=("_order","_product"))
    cat_col="category_product" if "category_product" in cat_source.columns else ("category" if "category" in cat_source.columns else "category_order")
    most_cat=cat_source.groupby("customer_id")[cat_col].agg(lambda x:x.mode().iloc[0] if not x.mode().empty else "Unknown").rename("most_frequent_category")
    feat=feat.merge(most_cat,on="customer_id",how="left")
    feat=feat.replace([np.inf,-np.inf],np.nan)
    numeric=["recency","frequency","monetary","avg_discount","cancellation_rate","avg_delivery","age","tenure_days"]
    categorical=["city","gender","most_frequent_category"]
    feat[numeric]=feat[numeric].fillna(feat[numeric].median())
    X=feat[numeric+categorical]; y=feat["lapsed"]
    X_train,X_test,y_train,y_test=train_test_split(X,y,test_size=.2,random_state=42,stratify=y)
    preproc=ColumnTransformer([
        ("num",Pipeline([("imputer",SimpleImputer(strategy="median")),("scale",StandardScaler())]),numeric),
        ("cat",Pipeline([("imputer",SimpleImputer(strategy="most_frequent")),("onehot",OneHotEncoder(handle_unknown="ignore",drop="first"))]),categorical)])
    lr=Pipeline([("prep",preproc),("model",LogisticRegression(max_iter=1000))])
    gs=GridSearchCV(lr,{"model__C":[.01,.1,1,10,100]},scoring="f1",cv=5,n_jobs=-1)
    gs.fit(X_train,y_train)
    rf=Pipeline([("prep",preproc),("model",RandomForestClassifier(n_estimators=100,random_state=42))])
    gsrf=GridSearchCV(rf,{"model__max_depth":[3,5,8],"model__min_samples_leaf":[5,10,20]},scoring="f1",cv=5,n_jobs=-1)
    gsrf.fit(X_train,y_train)
    models={"LogisticRegression":gs.best_estimator_,"RandomForest":gsrf.best_estimator_}
    results=[]
    for name,model in models.items():
        pred=model.predict(X_test)
        row={"model":name,"best_params":str(gs.best_params_ if name=="LogisticRegression" else gsrf.best_params_),
             "accuracy":accuracy_score(y_test,pred),"precision":precision_score(y_test,pred,zero_division=0),
             "recall":recall_score(y_test,pred,zero_division=0),"f1":f1_score(y_test,pred,zero_division=0),
             "confusion_matrix":str(confusion_matrix(y_test,pred).tolist())}
        results.append(row)
        print(row)
    chosen=models["RandomForest"] if f1_score(y_test,models["RandomForest"].predict(X_test))>=f1_score(y_test,models["LogisticRegression"].predict(X_test)) else models["LogisticRegression"]
    # training-only random oversampling for LR; evaluate against same original test set
    train_df=X_train.copy(); train_df["__y"]=y_train.values
    pos=train_df[train_df.__y==1]
    neg=train_df[train_df.__y==0]
    if len(pos) and len(pos)<len(neg):
        add=pos.sample(n=len(neg)-len(pos),replace=True,random_state=42)
        balanced=pd.concat([train_df,add],ignore_index=True)
        lr_bal=Pipeline([("prep",preproc),("model",LogisticRegression(max_iter=1000,C=gs.best_params_["model__C"]))])
        lr_bal.fit(balanced[numeric+categorical],balanced["__y"])
        pred=lr_bal.predict(X_test)
        over_metrics={"precision":precision_score(y_test,pred,zero_division=0),"recall":recall_score(y_test,pred,zero_division=0),"f1":f1_score(y_test,pred,zero_division=0)}
        pd.DataFrame([over_metrics]).to_csv(OUT/"oversampled_lr_metrics.csv",index=False)
        print("Oversampled LR",over_metrics)
    joblib.dump(chosen,OUT/"lapse_model.joblib")
    loaded=joblib.load(OUT/"lapse_model.joblib")
    assert np.array_equal(chosen.predict(X_test),loaded.predict(X_test))
    results_df=pd.DataFrame(results); results_df.to_csv(OUT/"lapse_model_metrics.csv",index=False)
    probs=chosen.predict_proba(X_test)[:,1]
    retention=pd.DataFrame({"customer_id":X_test.index.map(lambda i:feat.loc[i,"customer_id"]),"lapse_probability":probs,"actually_lapsed":y_test.values})
    retention=retention.merge(rfm[["customer_id","is_premium"]],on="customer_id",how="left")
    retention=retention[retention.is_premium.eq(1)].sort_values("lapse_probability",ascending=False).head(10)
    retention[["customer_id","lapse_probability","actually_lapsed"]].to_csv(OUT/"retention_list.csv",index=False)
    print("Retention list rows:",len(retention))
if __name__=="__main__": run()
