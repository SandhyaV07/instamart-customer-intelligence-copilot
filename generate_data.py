"""Deterministic synthetic Instamart-style data generator for the capstone."""
from pathlib import Path
import numpy as np
import pandas as pd
import random

SEED = 42
OUT = Path("data/raw")
OUT.mkdir(parents=True, exist_ok=True)

def main():
    rng = np.random.default_rng(SEED)
    random.seed(SEED)
    n_customers, n_products, n_orders = 1200, 40, 12965
    cities = ["Chennai", "Bengaluru", "Mumbai", "Delhi", "Hyderabad", "Pune"]
    city_spellings = {
        "Chennai": ["Chennai", " CHENNAI", "chennai ", "Chennai "],
        "Bengaluru": ["Bengaluru", "BANGALORE", "bengaluru ", " Bangalore"],
        "Mumbai": ["Mumbai", " MUMBAI", "mumbai "],
        "Delhi": ["Delhi", " DELHI", "delhi "],
        "Hyderabad": ["Hyderabad", " HYDERABAD", "hyderabad "],
        "Pune": ["Pune", " PUNE", "pune "],
    }
    genders = ["Male", "Female", "Unknown"]
    customer_rows = []
    for i in range(n_customers):
        city = cities[i % len(cities)]
        gender = "Male" if i % 2 == 0 else "Female"
        raw_gender = gender
        if i < 30: raw_gender = ""
        elif i % 19 == 0: raw_gender = "MALE" if gender == "Male" else "FEMALE"
        elif i % 23 == 0: raw_gender = "m" if gender == "Male" else "f"
        elif i % 29 == 0: raw_gender = " unknown "
        age = int(rng.integers(18, 71))
        if i < 61: age = np.nan
        if i in range(61,67): age = [8, 9, 101, 102, 5, 110][i-61]
        signup = pd.Timestamp("2023-01-01") + pd.Timedelta(days=int(rng.integers(0, 900)))
        raw_city = city_spellings[city][i % len(city_spellings[city])]
        customer_rows.append([f"C{i+1:04d}", raw_city, raw_gender, age, signup.date().isoformat()])
    customers = pd.DataFrame(customer_rows, columns=["customer_id","city","gender","age","signup_date"])
    # ensure canonical city distribution from the brief after cleaning
    target_counts = {"Pune":227,"Delhi":210,"Bengaluru":197,"Chennai":191,"Hyderabad":191,"Mumbai":184}
    city_values = []
    for city, count in target_counts.items(): city_values += [city]*count
    rng.shuffle(city_values)
    customers["city"] = [city_spellings[c][j % len(city_spellings[c])] for j,c in enumerate(city_values)]
    # Ensure 560 male, 610 female, 30 blank/unknown after mapping.
    g = ["Male"]*560 + ["Female"]*610 + [""]*30
    rng.shuffle(g)
    customers["gender"] = g
    customers.to_csv(OUT/"customers.csv", index=False)

    categories = ["Produce","Dairy","Snacks","Beverages","Household","Personal Care","Electronics","Bakery"]
    products = pd.DataFrame({
        "product_id":[f"P{i+1:03d}" for i in range(n_products)],
        "product_name":[f"Product {i+1:02d}" for i in range(n_products)],
        "category":[categories[i % len(categories)] for i in range(n_products)],
        "price":np.round(rng.uniform(25,1500,n_products),2)
    })
    products.to_csv(OUT/"products.csv", index=False)

    product_map = products.set_index("product_id")
    order_rows=[]
    start=pd.Timestamp("2024-10-01")
    for i in range(n_orders):
        cid=f"C{int(rng.integers(1,n_customers+1)):04d}"
        pid=f"P{int(rng.integers(1,n_products+1)):03d}"
        qty=int(rng.integers(1,5))
        discount=int(rng.choice([0,0,0,5,10,15,20,25]))
        status="completed" if rng.random()<0.91 else "cancelled"
        dt=start+pd.Timedelta(days=int(rng.integers(0,365)), hours=int(rng.integers(0,24)))
        price=float(product_map.loc[pid,"price"])
        amount=round(price*qty*(1-discount/100),2)
        delivery=float(rng.integers(10,61)) if status=="completed" else np.nan
        if i % 109 == 0: amount="N/A"
        if i % 123 == 0: delivery=-int(rng.integers(1,20))
        if i % 5 == 0: delivery=np.nan if status=="completed" else delivery
        order_rows.append([f"ORD-{i+1:06d}",cid,pid,dt.isoformat(sep=" "),qty,discount,amount,status,delivery])
    orders=pd.DataFrame(order_rows,columns=["order_id","customer_id","product_id","order_date","quantity","discount_pct","amount","status","delivery_minutes"])
    # Mark 656 rows pending before duplication so duplicated rows remain exact.
    orders.loc[orders.index[:656], "status"] = "pending"
    # Force 120 nonnumeric amounts before duplication.
    orders.loc[orders.index[1000:1120], "amount"] = "N/A"
    # Add exactly 119 exact duplicate rows; total raw orders is 13,084.
    orders = pd.concat([orders, orders.iloc[:119]], ignore_index=True)
    orders.to_csv(OUT/"orders.csv", index=False)

    ticket_rows=[]
    categories_t=["billing","delivery","technical","fraud"]
    for i in range(164):
        cat=categories_t[i%4]
        msg = {
            "billing": "I was charged twice for my recent order and need a refund.",
            "delivery": "My order is late and the delivery partner has not arrived.",
            "technical": "The app crashes when I try to complete checkout.",
            "fraud": "I do not recognize this payment and suspect fraudulent activity."
        }[cat]
        if i%7==0: msg += " Contact me at customer@example.com."
        if i%5==0: msg += " My phone is 9876543210."
        if i%11==0: msg += f" The order is ORD-{i+1:06d}."
        if i%41==0: msg = "   "
        if i%37==0: msg = " ".join(["long ticket text"]*120)
        ticket_rows.append([f"T{i+1:04d}", f"C{int(rng.integers(1,n_customers+1)):04d}", msg, cat])
    tickets=pd.DataFrame(ticket_rows,columns=["ticket_id","customer_id","message","true_category"])
    tickets.to_csv(OUT/"tickets.csv",index=False)
    print("generated: customers=1200 products=40 orders_raw=13084 tickets=164")

if __name__=="__main__":
    main()
