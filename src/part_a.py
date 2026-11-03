from pathlib import Path
import sys, sqlite3
import numpy as np, pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parent))
from common import ROOT,RAW,CLEAN,OUT,DB,connect

def run():
    customers=pd.read_csv(RAW/"customers.csv")
    products=pd.read_csv(RAW/"products.csv").rename(columns={"price_inr":"price"})
    orders=pd.read_csv(RAW/"orders.csv").rename(columns={"order_ts":"order_date","order_amount":"amount"})
    # Normalize customers
    customers["city"]=customers["city"].fillna("").astype(str).str.strip().str.title().replace({"":"Unknown","Banglore":"Bengaluru","Bangalore":"Bengaluru"})
    customers["city"]=customers["city"].replace({"Bangalore":"Bengaluru"})
    customers["gender"]=customers["gender"].fillna("").astype(str).str.strip().str.lower().map(
        lambda x: "Male" if x in ("male","m") else ("Female" if x in ("female","f") else ("Unknown" if x in ("","unknown","nan") else "Unknown")))
    customers["age"]=pd.to_numeric(customers["age"],errors="coerce")
    customers.loc[~customers["age"].between(10,100),"age"]=np.nan
    customers["age"]=customers["age"].fillna(customers.groupby("city")["age"].transform("median"))
    customers["signup_date"]=pd.to_datetime(customers["signup_date"],errors="coerce")
    # Normalize orders and deduplicate
    orders["order_date"]=pd.to_datetime(orders["order_date"],errors="coerce")
    raw_dupes=int(orders.duplicated().sum())
    orders=orders.drop_duplicates()
    orders=orders.sort_values("order_date").drop_duplicates("order_id",keep="last")
    # Pending rows are excluded from the analytic order table after they are counted in the raw audit.
    orders=orders[orders["status"].astype(str).str.lower()!="pending"].copy()
    orders["quantity"]=pd.to_numeric(orders["quantity"],errors="coerce")
    orders["discount_pct"]=pd.to_numeric(orders["discount_pct"],errors="coerce").fillna(0)
    orders["amount"]=pd.to_numeric(orders["amount"],errors="coerce")
    price=products.set_index("product_id")["price"]
    missing=orders["amount"].isna()
    orders.loc[missing,"amount"]=orders.loc[missing,"product_id"].map(price)*orders.loc[missing,"quantity"]*(1-orders.loc[missing,"discount_pct"]/100)
    orders["delivery_minutes"]=pd.to_numeric(orders["delivery_minutes"],errors="coerce")
    orders.loc[orders["delivery_minutes"]<0,"delivery_minutes"]=np.nan
    # category-based completed-delivery imputation
    orders=orders.merge(products[["product_id","category"]],on="product_id",how="left")
    med=orders.loc[orders.status.eq("completed")].groupby("category")["delivery_minutes"].median()
    m=orders.status.eq("completed") & orders.delivery_minutes.isna()
    orders.loc[m,"delivery_minutes"]=orders.loc[m,"category"].map(med)
    # retain cancelled delivery missing
    for df,name in [(customers,"customers"),(products,"products"),(orders,"orders")]:
        df.to_csv(CLEAN/f"{name}.csv",index=False)
    with connect() as con:
        customers.to_sql("customers",con,if_exists="replace",index=False)
        products.to_sql("products",con,if_exists="replace",index=False)
        orders.to_sql("orders",con,if_exists="replace",index=False)
    # validation checkpoints
    with connect() as con:
        checks=[
            ("customers_rows",con.execute("select count(*) from customers").fetchone()[0]==1200),
            ("products_rows",con.execute("select count(*) from products").fetchone()[0]==40),
            ("orders_unique_ids",con.execute("select count(*)=count(distinct order_id) from orders").fetchone()[0]),
            ("amount_nonmissing",con.execute("select count(*) from orders where amount is null").fetchone()[0]==0),
            ("no_negative_delivery",con.execute("select count(*) from orders where delivery_minutes<0").fetchone()[0]==0),
            ("valid_age",con.execute("select count(*) from customers where age is not null and (age<10 or age>100)").fetchone()[0]==0),
            ("gender_allowed",con.execute("select count(*) from customers where gender not in ('Male','Female','Unknown')").fetchone()[0]==0),
            ("all_tables",con.execute("select count(*) from sqlite_master where type='table' and name in ('customers','products','orders')").fetchone()[0]==3),
        ]
    if not all(v for _,v in checks):
        print("CHECKPOINTS FAILED",[(k,v) for k,v in checks if not v]); raise SystemExit(1)
    print("ALL CHECKPOINTS PASSED")
    print(f"raw_exact_duplicates={raw_dupes}")
    print(f"clean_orders={len(orders)} completed={(orders.status=='completed').sum()} cancelled={(orders.status=='cancelled').sum()}")
    print(f"completed_revenue_INR={orders.loc[orders.status=='completed','amount'].sum():.2f}")
if __name__=="__main__": run()
