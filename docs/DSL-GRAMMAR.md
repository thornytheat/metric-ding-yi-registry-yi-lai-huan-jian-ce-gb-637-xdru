# 指标 DSL 文法

一行一条定义，空行与 `#` 开头的注释行不参与解析。

```text
definition := name '=' expr clause*
clause     := 'where' field '=' value
            | 'group' 'by' dim (',' dim)*
            | 'depends' ':' name (',' name)*
expr       := term (('+' | '-') term)*
term       := factor (('*' | '/') factor)*
factor     := agg '(' field ')'
            | 'ref' '(' name ')'
            | number
            | '(' expr ')'
agg        := 'SUM' | 'AVG' | 'MIN' | 'MAX' | 'COUNT' | 'COUNT_DISTINCT'
number     := 十进制数字，可带小数部分
```

## 归一化

分析前先做字符归一：

- `U+FF01`–`U+FF5E` 全角 ASCII 转半角（全角逗号、括号、等号、加减号、数字）；
- 顿号 `、` 视为逗号，句号 `。` 视为点，全角空格视为半角空格；
- 归一后再分词，所以 `SUM（order_amt）－SUM（refund_amt）` 与半角写法等价。

## 聚合与中性别名

| 登记名 | 含义 | 可接受的中文写法 |
|---|---|---|
| SUM | 求和 | 求和、合计 |
| AVG | 平均 | 平均、均值 |
| MIN | 最小 | 最小 |
| MAX | 最大 | 最大 |
| COUNT | 计数 | 计数 |
| COUNT_DISTINCT | 去重计数 | 去重计数 |

## 示例

```text
销售额 = SUM(order_amt) - SUM(refund_amt) group by store_id,order_date
毛利率 = ref(毛利额) / ref(销售额) depends: 毛利额,销售额
退款率 = SUM(refund_amt) / SUM(order_amt) where channel = 线上 group by channel
件单价 = SUM(order_amt) / SUM(qty) group by category
```

## 错误码对照

| 写法 | 原因码 |
|---|---|
| 没有 `=` | Q_NO_ASSIGN |
| `=` 左边不是合法指标名 | Q_NAME_INVALID |
| `=` 右边为空、运算符后没有项 | Q_EXPR_EMPTY |
| 括号多一个或少一个、嵌套过深 | Q_PAREN_UNBALANCED |
| 表达式后还有记号 | Q_TOKEN_EXTRA |
| 聚合不在白名单 | Q_AGG_UNKNOWN |
| 聚合参数不是单字段、嵌套聚合 | Q_AGG_ARITY |
| 字段不在登记表、别名也未命中 | Q_FIELD_UNKNOWN |
| 字段位置是空值哨兵 | Q_SENTINEL_VALUE |
| 过滤条件不是单字段等值 | Q_WHERE_INVALID |
| 分组字段不是维度 | Q_GROUP_INVALID |
| 与前面某行定义完全相同 | Q_DUP_LINE |
