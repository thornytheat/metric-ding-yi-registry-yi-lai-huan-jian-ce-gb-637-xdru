"""脏样例跑出来的确定值：改样例必须同步改这里，测试会立刻报出来。"""

LINES_TOTAL = 59
LINES_REGISTERED = 26
LINES_ISOLATED = 18
BLANK_LINES = 7
COMMENT_LINES = 8

NODES_TOTAL = 46
EDGES_TOTAL = 67
REPORTS_TOTAL = 10
REPORTS_RESOLVED = 9

CYCLE_COMPONENTS = 3
CYCLE_METRICS = 6
CONFLICTS = 3

DIAG_TOTAL = 31

FIELD_NODES = 6
DIM_NODES = 5

CONFLICT_ROWS = (
    ("门店销售额", "BLOCK", 10, 31),
    ("销售额", "REVIEW", 3, 32),
    ("毛利额", "INFO", 4, 33),
)

CYCLE_MEMBER_SETS = (
    ("动销率", "库存深度", "周转天数"),
    ("净增量", "基期销售额"),
    ("自比值",),
)

VERSION_ROWS = 10
VERSION_OVERLAP = 2
VERSION_INVERTED = 1
VERSION_UNKNOWN = 1

REGISTERED_NAMES = (
    "销售额", "毛利额", "毛利率", "客单价", "订单数", "退款率", "渠道销售额",
    "门店销售额", "访客数", "件单价", "品类销售额", "城市销售额", "净增量",
    "基期销售额", "动销率", "库存深度", "周转天数", "自比值", "全角写法",
    "全角分组", "别名命中", "中文聚合", "大数常量", "声明多余", "未声明引用",
    "悬空引用",
)

BIG_NUMBER = "123456789012345678901234567890"
