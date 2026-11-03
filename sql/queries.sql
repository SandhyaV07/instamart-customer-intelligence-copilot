-- Q1: customers with high order count
SELECT c.customer_id, c.city, COUNT(o.order_id) AS completed_orders
FROM customers c JOIN orders o USING(customer_id)
WHERE o.status='completed'
GROUP BY c.customer_id,c.city
HAVING COUNT(o.order_id)>=15
ORDER BY completed_orders DESC
LIMIT 30;

-- Q2: city/category revenue
SELECT c.city,p.category,ROUND(SUM(o.amount),2) AS revenue_inr
FROM orders o JOIN customers c USING(customer_id) JOIN products p USING(product_id)
WHERE o.status='completed'
GROUP BY c.city,p.category
ORDER BY revenue_inr DESC;

-- Q3: products priced above catalogue average
SELECT product_id,product_name,price FROM products
WHERE price>(SELECT AVG(price) FROM products) ORDER BY price DESC;

-- Q4: customers without completed orders
SELECT c.customer_id FROM customers c
WHERE NOT EXISTS (SELECT 1 FROM orders o WHERE o.customer_id=c.customer_id AND o.status='completed');

-- Q5: CTE customers spending above average completed spend
WITH spend AS (
 SELECT customer_id,SUM(amount) AS monetary FROM orders WHERE status='completed' GROUP BY customer_id
)
SELECT customer_id,monetary FROM spend
WHERE monetary>(SELECT AVG(monetary) FROM spend) ORDER BY monetary DESC;

-- Q6: rank customers within each city
WITH spend AS (
 SELECT c.city,c.customer_id,SUM(o.amount) AS spend
 FROM customers c JOIN orders o USING(customer_id)
 WHERE o.status='completed' GROUP BY c.city,c.customer_id
)
SELECT city,customer_id,spend,RANK() OVER(PARTITION BY city ORDER BY spend DESC) AS spend_rank
FROM spend ORDER BY city,spend_rank;

-- Q7: daily cumulative completed revenue
WITH daily AS (
 SELECT date(order_date) AS order_day,SUM(amount) AS revenue
 FROM orders WHERE status='completed' GROUP BY date(order_date)
)
SELECT order_day,revenue,SUM(revenue) OVER(ORDER BY order_day ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS cumulative_revenue
FROM daily ORDER BY order_day;
