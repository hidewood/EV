ERROR_CODES = {
    0: "success",
    1001: "参数校验失败",
    1002: "未登录或 token 过期",
    1003: "权限不足",
    2001: "用户不存在",
    2002: "密码错误",
    2003: "用户已注册",
    3001: "已有未完成请求",
    3002: "请求不存在",
    3003: "不允许在此状态下修改",
    3004: "车辆不在等候区",
    3005: "等候区已满",
    4001: "充电桩不存在",
    4002: "充电桩状态不允许操作",
    4003: "充电桩无空位",
    5001: "调度策略执行失败",
    6001: "账单不存在",
}


def success(data=None, message="success"):
    return {"code": 0, "message": message, "data": data}


def error(code, message=None):
    msg = message or ERROR_CODES.get(code, "未知错误")
    return {"code": code, "message": msg, "data": None}
