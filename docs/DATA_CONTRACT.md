# 数据契约 / Excel 导入规范

## 1. 推荐核心数据表

| 表 | 主要字段 | 约束/用途 |
|---|---|---|
| users | id,username,password_hash,role,department,is_active | 身份、权限；使用框架标准 auth 模型 |
| spare_items | id,preferred_new_code,description,category,equipment,brand,location,unit,status,created_at,updated_at | id 是主键；料号不能作为全局主键 |
| spare_aliases | id,spare_id,code,code_type,source_record_id,verified | 保存旧料号、备选料号、错列候选料号；允许一个 item 多个编码 |
| source_files | id,sha256,original_filename,relative_path,uploaded_by,uploaded_at,template_kind,status | 以哈希幂等；保留文件原件；相同哈希多路径保留 location 映射 |
| source_rows | id,source_file_id,sheet_name,excel_row,raw_json,import_status,issue_list,linked_spare_id | 单行审计；来源索引 `source_file,sheet,row` |
| application_batches | id,year,month,kind,requester,department,status,version,source_file_id,revision_parent_id,created_at,submitted_at | 单次申请单头；kind=spare_purchase/department_purchase |
| application_lines | id,batch_id,spare_id,raw_new_code,raw_old_code,raw_description,equipment,attribute,customer,line_name,quantity_decimal,unit,raw_quantity,... | 行级明细；保留源快照；数量 Decimal, 单位独立 |
| approval_events | id,batch_id,actor,action,comment,created_at,before_status,after_status | 所有审核和退回可追溯 |
| audit_logs | id,actor,target_type,target_id,action,before_json,after_json,created_at | 主数据修改/导入/删除/合并留痕 |
| inventory_snapshots | id,spare_id,year,month,warehouse,stock_qty,on_order_qty,unit,source_record_id,as_of | 非实时库存；只导出快照，不擅自累减 |

`application_lines` 需要覆盖主表所有 21 个字段，推荐使用以下稳定英文标识：

```
old_material_code, new_material_code, material_description, equipment_name,
material_attribute, safety_stock, machine_count_per_line, usage_per_machine,
lifetime_months, line_name, theoretical_monthly_qty,
previous_month_actual_qty, forecast_qty, customer, section_manager,
factory_stock, outstanding_qty, nvb2, required_purchase_qty, remark, order_number
```

推荐配合 `source_values_json` 和 `source_headers_json` 保留原始取值和原表头；文本字段不以 `0`/`-` 代表缺失。建议所有数量和金额以 `Decimal` 保存，显示单位，在数据库层不要用 float。

## 2. 主模板按标题映射（不是按列写死）

| 业务字段 | 21列主表 | 18列表（8月工程二部） | 17列表（9月工程二部） |
|---|---|---|---|
| new_material_code | B 新建料号 | A 新建料号 | B 新建料号 |
| old_material_code | A 原物料 | 通常不存在 | A 原物料 |
| material_description | C 物料描述 | B 物料描述 | C 物料描述 |
| equipment_name | D 使用设备 | C 使用设备 | D 使用设备 |
| material_attribute | E 属性 | D 属性 | E 属性 |
| safety_stock | F 安全库存 | E 安全库存 | F 安全库存 |
| machine_count_per_line | G 设备数量/1条大线 | F | G |
| usage_per_machine | H 备件使用量/1台设备 | G | H |
| lifetime_months | I 使用寿命(以月为单位) | H | I |
| line_name | J 线体 | I | J |
| theoretical_monthly_qty | K 月需求量/理论 | J | K |
| previous_month_actual_qty | L X月份实际 | 未配置 | 未配置 |
| forecast_qty | M X月预估 | K 8月预估 | L 9月预估 |
| customer | N 客户别 | P 客户别 | O 客户别 |
| section_manager | O 科长 | Q 科长 | P 科长 |
| factory_stock | P 全厂库存 | M/O 库存（多列，应标记待确认） | Q 全厂库存 |
| outstanding_qty | Q 未交 | L/N 未交（多列，应标记待确认） | M 未交 |
| nvb2 | R NVB2 | 不存在 | 不存在 |
| required_purchase_qty | S 需要请购 | 不存在 | 不存在 |
| remark | T 备注 | 不存在/扩展列 | 不存在 |
| order_number | U 单号 | R 第18列可能是单号（无表头，待确认） | 不存在 |

**不能在18列将两组“库存/未交”任选其一且不告知用户**：导入预览要分别显示，必要时让用户映射。无标头 R 列不能自作主张把它当正式单号。

## 3. 基础料号表

基础资料分不同设备 sheet，列标题和业务含义不一致：

- 通用字段优先匹配中文标题：`新料号`、`旧料号`、`厂内物料说明`、`供应商物料说明`、`品牌`、`备件品牌`、`设备/设备名称/设备型号`、`主要名称`、`使用位置`、`单机台使用数量`、`使用寿命`、`备注`。
- `贴胶带设备` 仅 A 列新料号、B 列内部描述；`轨道/暂存机` 为 A 旧料号、B 新料号。
- `NPM+SPG` 部分 A 新料号缺失而 B 旧料号有值；不要删除或倒置标记。有的 A/B 都是类似料号字符串，必须保留原有标注。
- `ASM` 数行在 C“厂内物料说明”列放 `5321.*` 样式料号，D 是描述；应作为**待人工确认的料号候选**，同时保留 C/D 原值。
- `其他料号`、`Relfow`、`钢片机` 很多数据无新料号但有旧料号/描述；应保留临时 item。
- `Sheet1` 和 `Sheet2` 不是备件料号表；`领用记录` 是历史领用事实，不是采购申请。

## 4. 申请月份逻辑

保留 `source_folder_month`、`filename_month_candidate`、`header_month_candidate`、`approved_effective_year_month` 四个字段。前 3 个只做候选，最后一个经确认后用于报表。

- 常见月份动态标题：`12月份实际` / `1月预估`、`9月份实际` / `10月预估`。
- 已发现 `20268月份费用预估-周明光_.xlsx` 的备件购买 header 为 `7月预估`，但部门自购为 `8月预估`；不同 sheet 必须分别处理。
- `20267月份费用预估-周明光_.xlsx` 的备件购买存在 `0月份实际`，不合法，应提醒而非自动改成 6 月。
- `20251月份费用预估-周明光_.xlsx` 的表头显示 `12月预估` 而文件名显示 1 月，不能按当前文件夹覆盖。
- `202512月份费用预估-周明光1.4新增_.xlsx` 与同目录其他12月版本相互独立，按 source_file_hash 保留版本候选。

## 5. 数值/单位/空值

- 原表可能出现 `200m`、`100m`、`50m`；安全解析 Decimal + unit=m；原始内容必须保留。
- `-` 表示原文占位，不可无条件等价为零。Excel 错误如 `#N/A` 应标为异常，不可导出计算为 0。
- 空白申请数量不是 0：该行可以存草稿、待确认，但不可进入求和；`0` 是明确0。
- 数量单位同一分组不一致，不可聚合；如 `200 m` 与 `20 pcs` 必须分别汇总。
- 理论月需求的旧公式结果作为源字段保存；用户没提供统一公式，不强制后台自行计算。
- `NVB2`、全厂库存、未交是不同业务字段；不可猜业务对应关系和库存计算公式。

## 6. 去重/版本/修订

- 同源二进制 SHA256 = 相同文件版本；重复导入返回已有 source_file 与状态，不创建额外单据/行。
- 同名称、不同内容 = 两个源版本；同内容、不同路径 = 同版本多个来源位置（应记录路径，不能重复业务量）。
- 历史不同版本若月份/申请人相同，**绝不简单累加**；先由管理员确认有效版本。生效选择动作要写审计日志。
- 标准物料关联优先已验证料号/别名，随后文字辅助建议；同号异物必须人工确认，不以描述相似强行合并。
- 申请主单使用 `revision_parent_id` 和 version；退回修改/审批后修订都需有审计、版本避免并发覆盖。

## 7. 导出契约

- 主要导出 21列 A～U，按年月生成动态 L/M 标题，保留两个业务 sheet，业务值按列回填。
- 保存为可在 Excel 中打开的 xlsx，不得新增隐藏业务数值污染表；不带旧申请的数据行。
- 原料号/数字字符串不得由 Excel 自动转换为科学计数法；防止公式注入（用户录入描述以 `=`/`+`/`@` 起头时当作文本）。
- 原模板的行高、列宽、格式、筛选/打印设置尽可能保留。保留不同月份的标题习惯，但不沿用历史错误表头。
- 至少自动验证：sheet 名称、21列字段顺序、动态表头、生成行数/数量/单位/料号与数据库相符、无意外隐私行和可重复读取。
