# 干净样例：8 个定义，无环、无未声明引用
销售额 = SUM(order_amt) - SUM(refund_amt) group by store_id,order_date
毛利额 = SUM(order_amt) - SUM(cost_amt) group by store_id
毛利率 = ref(毛利额) / ref(销售额) depends: 毛利额,销售额
客单价 = AVG(order_amt) group by store_id
订单数 = COUNT(order_id) group by store_id,order_date
渠道销售额 = SUM(order_amt) group by channel
退款率 = SUM(refund_amt) / SUM(order_amt) group by channel
净增量 = SUM(order_amt) - SUM(refund_amt) group by store_id
