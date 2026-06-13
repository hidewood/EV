-- 小容量手动验收演示重置脚本
--
-- 使用场景：
-- 1. 先启动后端并进入管理员端。
-- 2. 在“系统参数”中保存：
--    快充桩数 = 1，慢充桩数 = 1，等候区容量 N = 1，桩队列长度 M = 1，
--    扩展调度模式 = 普通调度(normal)。
-- 3. 执行本脚本，把数据库恢复到一个很小、很容易手动塞满的状态。
-- 4. 手动注册/登录 3 个左右用户，即可演示排队、满位、修改、取消、结束充电。
--
-- 注意：这是演示库专用脚本。为了保证场景干净，会清空当前排队区/充电区队列，
-- 并把所有未完成的充电请求置为 cancelled。

START TRANSACTION;

DELETE FROM `waiting_queue`;
DELETE FROM `pile_queue`;
DELETE FROM `dispatch_record`;
UPDATE `charging_session`
SET `status` = 'interrupted',
    `end_time` = COALESCE(`end_time`, NOW())
WHERE `status` = 'active';
UPDATE `charging_request`
SET `status` = 'cancelled',
    `modify_time` = NOW()
WHERE `status` IN ('queuing', 'dispatched', 'charging', 'pending_reschedule');

UPDATE `charging_pile`
SET `status` = 'off',
    `queue_len` = 1
WHERE `pile_id` NOT IN (1, 3);

INSERT INTO `charging_pile`
    (`pile_id`, `mode`, `power`, `status`, `queue_len`, `total_charge_num`, `total_charge_time`, `total_charge_capacity`)
VALUES
    (1, 'F', 30.0, 'available', 1, 0, 0.0, 0.0)
ON DUPLICATE KEY UPDATE
    `mode` = 'F',
    `power` = 30.0,
    `status` = 'available',
    `queue_len` = 1;

INSERT INTO `charging_pile`
    (`pile_id`, `mode`, `power`, `status`, `queue_len`, `total_charge_num`, `total_charge_time`, `total_charge_capacity`)
VALUES
    (3, 'T', 10.0, 'available', 1, 0, 0.0, 0.0)
ON DUPLICATE KEY UPDATE
    `mode` = 'T',
    `power` = 10.0,
    `status` = 'available',
    `queue_len` = 1;

COMMIT;

