# 星野零售 指标体系 2026-11 导出（含历史遗留定义）

销售额 = SUM(order_amt) - SUM(refund_amt) group by store_id,order_date
毛利额 = SUM(order_amt) - SUM(cost_amt) group by store_id
毛利率 = ref(毛利额) / ref(销售额) depends: 毛利额,销售额
客单价 = AVG(order_amt) group by store_id
订单数 = COUNT(order_id) group by store_id,order_date
退款率 = SUM(refund_amt) / SUM(order_amt) group by channel
渠道销售额 = SUM(order_amt) group by channel
门店销售额 = SUM(order_amt) group by store_id
访客数 = COUNT_DISTINCT(visitor_cnt) group by store_id,order_date
件单价 = SUM(order_amt) / SUM(qty) group by category
品类销售额 = SUM(order_amt) group by category
城市销售额 = SUM(order_amt) group by city
# 下面是衍生指标，历史版本里存在互相引用
净增量 = SUM(order_amt) - ref(基期销售额)
基期销售额 = ref(净增量) - SUM(refund_amt)
动销率 = ref(库存深度) / SUM(qty)
库存深度 = ref(周转天数) - ref(销售额)
周转天数 = ref(动销率) * 2
自比值 = ref(自比值) / SUM(order_amt)

# 录入遗留：全角标点、括号、别名写法
全角写法 = SUM（order_amt）－SUM（refund_amt）
全角分组 = SUM(order_amt) group by store_id，channel
别名命中 = SUM(order_amount) - SUM(退款金额) group by store_id
中文聚合 = 求和(order_amt) - 求和(refund_amt) group by channel
大数常量 = SUM(order_amt) - 123456789012345678901234567890

# 同名指标在三个 BI 里各写了一遍
门店销售额 = AVG(order_amt) group by store_id
销售额 = SUM(order_amt) - SUM(refund_amt) where channel = 线上 group by store_id,order_date
毛利额 = SUM(order_amt) - SUM(cost_amt) group by category
客单价 = AVG(order_amt) group by store_id

# 结构与取值错误
备注补全 = SUM(order_amt) 每月重跑
缺失括号 = SUM(order_amt) - SUM(refund_amt
未知聚合 = total(order_amt)
未知字段 = SUM(discount_amt)
哨兵字段 = SUM(N/A)
哨兵过滤 = SUM(order_amt) where channel = 未知
嵌套聚合 = MAX(AVG(order_amt))
分组越界 = SUM(order_amt) group by region
过滤越界 = SUM(order_amt) where region = 华东
尾部分隔符 = SUM(order_amt),
没有赋值号 SUM(order_amt)
= SUM(order_amt)
空表达式 =
负负得正 = SUM(order_amt) - -100

# 依赖声明与实际引用不一致
声明多余 = SUM(qty) depends: 销售额
未声明引用 = ref(毛利率) + SUM(qty)
悬空引用 = ref(已下线指标) + SUM(qty)

# 换行符混用的历史段落（下一行内含 U+2028 分隔符）
# 渠道定义统一后重跑 第二段说明保留在同一行

