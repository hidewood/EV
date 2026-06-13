-- 批量调度演示预置脚本
--
-- 使用场景：
-- 1. 先启动后端并进入管理员端。
-- 2. 在“系统参数”中保存：
--    快充桩数 = 1，慢充桩数 = 1，等候区容量 N = 1，桩队列长度 M = 2，
--    扩展调度模式 = 批量总时长最短(batch_min_total)。
-- 3. 再在 MySQL 中执行本脚本。
-- 4. 用任意普通用户账号提交一次充电请求，即可让等候车辆数达到全站容量并触发批量调度。
--
-- 注意：这是演示库专用脚本。为了保证场景可复现，会清空当前排队区/充电区队列，
-- 并把所有未完成的充电请求置为 cancelled。

START TRANSACTION;

-- 清理当前运行态，避免已有排队/会话干扰批量调度触发。
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

-- 清理上一次批量调度演示用户及其历史数据。
DELETE FROM `payment` WHERE `car_id` LIKE 'BATCH_DEMO_%';
DELETE FROM `bill` WHERE `car_id` LIKE 'BATCH_DEMO_%';
DELETE FROM `charging_detail` WHERE `car_id` LIKE 'BATCH_DEMO_%';
DELETE FROM `charging_session` WHERE `car_id` LIKE 'BATCH_DEMO_%';
DELETE FROM `charging_request` WHERE `car_id` LIKE 'BATCH_DEMO_%';
DELETE FROM `user` WHERE `car_id` LIKE 'BATCH_DEMO_%';

-- 只保留 1 个快充桩和 1 个慢充桩参与演示；队列长度与管理员端参数 M=2 保持一致。
UPDATE `charging_pile`
SET `status` = 'off',
    `queue_len` = 2
WHERE `pile_id` NOT IN (1, 3);

INSERT INTO `charging_pile`
    (`pile_id`, `mode`, `power`, `status`, `queue_len`, `total_charge_num`, `total_charge_time`, `total_charge_capacity`)
VALUES
    (1, 'F', 30.0, 'available', 2, 0, 0.0, 0.0)
ON DUPLICATE KEY UPDATE
    `mode` = 'F',
    `power` = 30.0,
    `status` = 'available',
    `queue_len` = 2;

INSERT INTO `charging_pile`
    (`pile_id`, `mode`, `power`, `status`, `queue_len`, `total_charge_num`, `total_charge_time`, `total_charge_capacity`)
VALUES
    (3, 'T', 10.0, 'available', 2, 0, 0.0, 0.0)
ON DUPLICATE KEY UPDATE
    `mode` = 'T',
    `power` = 10.0,
    `status` = 'available',
    `queue_len` = 2;

-- 预置 4 辆等待车。管理员端配置为 N=1、两根在线桩各 M=2 时，全站容量为 5。
-- 你再登录自己的账号提交第 5 辆车，后端会触发 batch_min_total 调度。
INSERT INTO `user`
    (`car_id`, `user_name`, `password_hash`, `car_capacity`, `role`, `created_at`)
VALUES
    ('BATCH_DEMO_A', '批量演示A', '$2b$12$6jqX/8Q5uxfTuEENw.uAve3zzHvFZapoL2cYkEbsYoOMl.rbt6JYq', 60.0, 'user', NOW()),
    ('BATCH_DEMO_B', '批量演示B', '$2b$12$6jqX/8Q5uxfTuEENw.uAve3zzHvFZapoL2cYkEbsYoOMl.rbt6JYq', 60.0, 'user', NOW()),
    ('BATCH_DEMO_C', '批量演示C', '$2b$12$6jqX/8Q5uxfTuEENw.uAve3zzHvFZapoL2cYkEbsYoOMl.rbt6JYq', 60.0, 'user', NOW()),
    ('BATCH_DEMO_D', '批量演示D', '$2b$12$6jqX/8Q5uxfTuEENw.uAve3zzHvFZapoL2cYkEbsYoOMl.rbt6JYq', 60.0, 'user', NOW());

INSERT INTO `charging_request`
    (`car_id`, `request_mode`, `request_amount`, `queue_num`, `status`, `pile_id`, `request_time`, `modify_time`)
VALUES
    ('BATCH_DEMO_A', 'F', 10.0, 'F1', 'queuing', NULL, NOW() - INTERVAL 4 MINUTE, NOW() - INTERVAL 4 MINUTE);
SET @req_a = LAST_INSERT_ID();
INSERT INTO `waiting_queue` (`request_id`, `mode`, `queue_num`, `join_time`)
VALUES (@req_a, 'F', 'F1', NOW() - INTERVAL 4 MINUTE);

INSERT INTO `charging_request`
    (`car_id`, `request_mode`, `request_amount`, `queue_num`, `status`, `pile_id`, `request_time`, `modify_time`)
VALUES
    ('BATCH_DEMO_B', 'F', 10.0, 'F2', 'queuing', NULL, NOW() - INTERVAL 3 MINUTE, NOW() - INTERVAL 3 MINUTE);
SET @req_b = LAST_INSERT_ID();
INSERT INTO `waiting_queue` (`request_id`, `mode`, `queue_num`, `join_time`)
VALUES (@req_b, 'F', 'F2', NOW() - INTERVAL 3 MINUTE);

INSERT INTO `charging_request`
    (`car_id`, `request_mode`, `request_amount`, `queue_num`, `status`, `pile_id`, `request_time`, `modify_time`)
VALUES
    ('BATCH_DEMO_C', 'T', 80.0, 'T1', 'queuing', NULL, NOW() - INTERVAL 2 MINUTE, NOW() - INTERVAL 2 MINUTE);
SET @req_c = LAST_INSERT_ID();
INSERT INTO `waiting_queue` (`request_id`, `mode`, `queue_num`, `join_time`)
VALUES (@req_c, 'T', 'T1', NOW() - INTERVAL 2 MINUTE);

INSERT INTO `charging_request`
    (`car_id`, `request_mode`, `request_amount`, `queue_num`, `status`, `pile_id`, `request_time`, `modify_time`)
VALUES
    ('BATCH_DEMO_D', 'T', 80.0, 'T2', 'queuing', NULL, NOW() - INTERVAL 1 MINUTE, NOW() - INTERVAL 1 MINUTE);
SET @req_d = LAST_INSERT_ID();
INSERT INTO `waiting_queue` (`request_id`, `mode`, `queue_num`, `join_time`)
VALUES (@req_d, 'T', 'T2', NOW() - INTERVAL 1 MINUTE);

COMMIT;

