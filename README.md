# MeetMate 多团队智能排期系统

MeetMate 是一个面向学习小组、工作团队、项目组、社团组织和朋友聚会的多人智能排期网页应用。系统将个人日程、Group 协作、成员空闲时间收集和智能推荐算法结合起来，帮助团队快速找到更合适的活动时间。

## 项目背景

多人协作时，经常需要在微信群、QQ群或表格中反复询问成员时间，信息分散且统计效率低。MeetMate 提供统一的个人日程管理和 Group 排期流程，能够自动检测个人日程冲突，并给出带评分和推荐理由的候选时间排序。

## 核心功能

1. 用户注册、登录和密码哈希存储。
2. 个人主页展示今日安排、近期提醒、Group 数量和本周活动数量。
3. 个人日程新增、查看、筛选、删除和冲突提醒。
4. 创建 Group、通过邀请码加入 Group。
5. Group 详情页展示成员、待排期活动和已确认活动。
6. Group 创建者创建待排期活动。
7. 成员对候选时间段提交“有空 / 不确定 / 没空”。
8. 智能排期算法根据成员空闲情况和个人日程冲突计算推荐结果。
9. Group 创建者确认最终时间，并同步到所有成员个人日程。
10. SQLite 数据持久化。

## 技术栈

- Python
- Streamlit
- SQLite
- pandas

## 安装方法

```bash
pip install -r requirements.txt
```

## 运行方法

```bash
streamlit run app.py
```

运行后，在浏览器中打开 Streamlit 提示的本地地址即可使用系统。

## 项目结构

```txt
.
├── app.py
├── auth.py
├── database.py
├── models.py
├── scheduler.py
├── ui_helpers.py
├── requirements.txt
├── README.md
├── test_cases.md
└── docs
    ├── database_design.md
    ├── project_plan_notes.md
    └── usecase.puml
```

## 数据库设计简介

系统使用 SQLite，启动时自动初始化数据表：

- `users`：用户账号、昵称和密码哈希。
- `groups`：Group 基本信息、邀请码和创建者。
- `group_members`：Group 成员和角色。
- `personal_events`：个人日程和已同步的 Group 活动。
- `group_activities`：待排期或已确认的 Group 活动。
- `availability`：成员对候选时间段的空闲状态。

详细设计见 `docs/database_design.md`。

## 智能排期算法

系统先根据候选日期、每日时间范围和活动时长生成候选时间段。每个候选时间段按以下规则评分：

```txt
基础得分 = 有空人数 * 1 + 不确定人数 * 0.5 + 没空人数 * 0
冲突惩罚 = 个人日程冲突人数 * 1
最终得分 = 基础得分 - 冲突惩罚
```

排序规则：

1. 最终得分越高越优先。
2. 得分相同时，个人日程冲突人数更少优先。
3. 再相同时，有空人数更多优先。
4. 再相同时，日期和时间更早优先。

## 测试用例说明

`test_cases.md` 覆盖注册、登录、创建 Group、加入 Group、添加个人日程、创建活动、提交空闲时间、智能排期、冲突检测和确认同步等核心流程。

## 后续改进方向

1. 增加日历视图。
2. 增加邮件或企业微信提醒。
3. 支持 ICS 日程导出。
4. 增加活动评论区。
5. 支持更细粒度的 Group 权限。
6. 接入真实日历系统。
7. 增加多人实时协同刷新。
