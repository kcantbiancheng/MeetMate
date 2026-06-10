from __future__ import annotations

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

import auth
import models
from database import init_db
from scheduler import (
    compute_recommendations,
    find_event_conflicts,
    generate_candidate_slots,
)
from ui_helpers import card, format_activity_time, format_event, inject_global_styles, tag


CHINA_TZ = ZoneInfo("Asia/Shanghai")
PAGE_OPTIONS = ["首页", "个人日程", "我的 Group", "智能排期", "设置"]
STATUS_LABEL_TO_VALUE = {"有空": "available", "不确定": "maybe", "没空": "unavailable"}
STATUS_VALUE_TO_LABEL = {value: label for label, value in STATUS_LABEL_TO_VALUE.items()}


def rerun() -> None:
    if hasattr(st, "rerun"):
        st.rerun()
    st.experimental_rerun()


def current_user() -> dict:
    return st.session_state["user"]


def set_page(page: str) -> None:
    st.session_state.page = page


def ensure_state() -> None:
    st.session_state.setdefault("page", "首页")
    st.session_state.setdefault("selected_group_id", None)
    st.session_state.setdefault("selected_activity_id", None)


def login_required() -> bool:
    return "user" in st.session_state and st.session_state["user"] is not None


def render_auth_page() -> None:
    st.markdown("<div style='height: 4rem'></div>", unsafe_allow_html=True)
    left, middle, right = st.columns([1, 1.2, 1])
    with middle:
        st.title("MeetMate")
        st.caption("让多人排期更简单")
        tab_login, tab_register = st.tabs(["登录", "注册"])

        with tab_login:
            with st.form("login_form"):
                username = st.text_input("用户名")
                password = st.text_input("密码", type="password")
                submitted = st.form_submit_button("登录", use_container_width=True)
            if submitted:
                ok, message, user = auth.login_user(username, password)
                if ok and user:
                    st.session_state.user = user
                    st.session_state.page = "首页"
                    st.success(message)
                    rerun()
                else:
                    st.error(message)

        with tab_register:
            with st.form("register_form"):
                username = st.text_input("用户名", key="register_username")
                password = st.text_input("密码", type="password", key="register_password")
                nickname = st.text_input("昵称")
                submitted = st.form_submit_button("注册", use_container_width=True)
            if submitted:
                ok, message = auth.register_user(username, password, nickname)
                if ok:
                    st.success(message)
                else:
                    st.error(message)


def render_sidebar() -> None:
    user = current_user()
    with st.sidebar:
        st.title("MeetMate")
        st.caption(f"你好，{user['nickname']}")
        st.divider()
        for page in PAGE_OPTIONS:
            button_type = "primary" if st.session_state.page == page else "secondary"
            if st.button(page, key=f"nav_{page}", use_container_width=True, type=button_type):
                st.session_state.page = page
                if page != "智能排期":
                    st.session_state.selected_activity_id = None
                rerun()
        st.divider()
        if st.button("退出登录", use_container_width=True):
            st.session_state.clear()
            rerun()


def render_home() -> None:
    user = current_user()
    now = datetime.now(CHINA_TZ)
    today = now.date()
    week_end = today + timedelta(days=6 - today.weekday())
    today_events = models.list_personal_events(user["id"], today, today)
    upcoming = models.get_upcoming_events(user["id"], now, 24)
    group_count = models.get_user_group_count(user["id"])
    week_count = models.count_events_between(user["id"], today, week_end)

    st.title(f"你好，{user['nickname']}")
    st.caption(f"今天是 {today.strftime('%Y-%m-%d')}")

    col1, col2, col3 = st.columns(3)
    col1.metric("加入的 Group", group_count)
    col2.metric("本周待参加活动", week_count)
    col3.metric("24 小时内提醒", len(upcoming))

    st.subheader("今日安排")
    if today_events:
        for row in today_events:
            card(row["title"], f"{row['start_time']} - {row['end_time']}", row.get("location") or "")
    else:
        st.info("今天暂无日程。")

    st.subheader("即将开始")
    if upcoming:
        for row in upcoming:
            card(row["title"], format_event(row), row.get("note") or "")
    else:
        st.info("未来 24 小时内暂无活动。")

    st.subheader("快捷入口")
    cols = st.columns(4)
    actions = [
        ("添加个人日程", "个人日程"),
        ("创建 Group", "我的 Group"),
        ("加入 Group", "我的 Group"),
        ("进入智能排期", "智能排期"),
    ]
    for col, (label, page) in zip(cols, actions):
        if col.button(label, use_container_width=True):
            st.session_state.page = page
            rerun()


def render_personal_events() -> None:
    user = current_user()
    st.title("个人日程")

    with st.expander("添加日程", expanded=True):
        with st.form("event_form"):
            title = st.text_input("标题")
            event_date = st.date_input("日期", value=date.today())
            col1, col2 = st.columns(2)
            start_time = col1.time_input("开始时间", value=time(9, 0))
            end_time = col2.time_input("结束时间", value=time(10, 0))
            location = st.text_input("地点")
            note = st.text_area("备注", height=90)
            event_type_label = st.selectbox("类型", ["个人", "Group"])
            submitted = st.form_submit_button("保存日程")
        if submitted:
            if not title.strip():
                st.error("标题不能为空。")
            elif start_time >= end_time:
                st.error("日程开始时间必须早于结束时间。")
            else:
                models.create_personal_event(
                    user_id=user["id"],
                    title=title,
                    event_date=event_date,
                    start_time=start_time,
                    end_time=end_time,
                    location=location,
                    note=note,
                    event_type="group" if event_type_label == "Group" else "personal",
                )
                st.success("日程已添加。")
                rerun()

    st.subheader("日程列表")
    filter_col, option_col = st.columns([1, 2])
    selected_date = filter_col.date_input("筛选日期", value=date.today(), key="event_filter_date")
    only_selected_day = option_col.checkbox("只显示该日期", value=False)
    if only_selected_day:
        events = models.list_personal_events(user["id"], selected_date, selected_date)
    else:
        events = models.list_personal_events(user["id"])

    conflicts = find_event_conflicts(events)
    if conflicts:
        st.warning(f"检测到 {len(conflicts)} 组日程时间冲突，请检查重叠安排。")

    if not events:
        st.info("暂无日程。")
        return

    for row in events:
        with st.container():
            col_main, col_action = st.columns([5, 1])
            type_text = "Group" if row["event_type"] == "group" else "个人"
            col_main.markdown(
                f"**{row['title']}**  {tag(type_text, 'green' if type_text == 'Group' else '')}",
                unsafe_allow_html=True,
            )
            col_main.caption(format_event(row))
            if row.get("note"):
                col_main.write(row["note"])
            if col_action.button("删除", key=f"delete_event_{row['id']}", use_container_width=True):
                models.delete_personal_event(user["id"], row["id"])
                st.success("日程已删除。")
                rerun()
            st.divider()


def render_group_card(row: dict) -> None:
    role_text = "创建者" if row["role"] == "owner" else "成员"
    with st.container():
        col_main, col_action = st.columns([5, 1])
        col_main.markdown(
            f"**{row['name']}**  "
            f"{tag(row.get('group_type') or '其他')} {tag(role_text, 'green' if row['role'] == 'owner' else '')}",
            unsafe_allow_html=True,
        )
        col_main.caption(
            f"成员 {row['member_count']} 人 · 待排期活动 {row['pending_count']} 个 · 邀请码 {row['invite_code']}"
        )
        if row.get("description"):
            col_main.write(row["description"])
        if col_action.button("进入", key=f"enter_group_{row['id']}", use_container_width=True):
            st.session_state.selected_group_id = row["id"]
            st.session_state.selected_activity_id = None
            st.session_state.page = "Group 详情"
            rerun()
        st.divider()


def render_groups() -> None:
    user = current_user()
    st.title("我的 Group")

    left, right = st.columns(2)
    with left:
        with st.expander("创建 Group", expanded=True):
            with st.form("create_group_form"):
                name = st.text_input("Group 名称")
                group_type = st.selectbox("Group 类型", models.GROUP_TYPES)
                description = st.text_area("Group 描述", height=100)
                submitted = st.form_submit_button("创建")
            if submitted:
                ok, message, group_id, _ = models.create_group(
                    user["id"], name, description, group_type
                )
                if ok:
                    st.success(message)
                    st.session_state.selected_group_id = group_id
                    st.session_state.page = "Group 详情"
                    rerun()
                else:
                    st.error(message)

    with right:
        with st.expander("加入 Group", expanded=True):
            with st.form("join_group_form"):
                invite_code = st.text_input("邀请码")
                submitted = st.form_submit_button("加入")
            if submitted:
                ok, message = models.join_group_by_invite(user["id"], invite_code)
                if ok:
                    st.success(message)
                    rerun()
                else:
                    st.error(message)

    groups = models.list_user_groups(user["id"])
    created = [row for row in groups if row["role"] == "owner"]
    joined = [row for row in groups if row["role"] != "owner"]

    st.subheader("我创建的 Group")
    if created:
        for row in created:
            render_group_card(row)
    else:
        st.info("你还没有创建 Group。")

    st.subheader("我加入的 Group")
    if joined:
        for row in joined:
            render_group_card(row)
    else:
        st.info("你还没有加入其他 Group。")


def render_group_detail() -> None:
    user = current_user()
    group_id = st.session_state.get("selected_group_id")
    if group_id is None:
        st.warning("请先选择一个 Group。")
        if st.button("返回我的 Group"):
            st.session_state.page = "我的 Group"
            rerun()
        return

    group = models.get_group(group_id)
    role = models.get_member_role(group_id, user["id"])
    if group is None or role is None:
        st.error("无法访问该 Group。")
        if st.button("返回我的 Group"):
            st.session_state.page = "我的 Group"
            rerun()
        return

    is_owner = group["owner_id"] == user["id"]
    if st.button("返回我的 Group"):
        st.session_state.page = "我的 Group"
        rerun()

    st.title(group["name"])
    st.markdown(
        f"{tag(group.get('group_type') or '其他')} {tag('创建者' if is_owner else '成员', 'green')}",
        unsafe_allow_html=True,
    )
    st.caption(f"邀请码：{group['invite_code']} · 创建者：{group['owner_name']} · 成员 {group['member_count']} 人")
    if group.get("description"):
        st.write(group["description"])

    if is_owner:
        with st.expander("编辑 Group 信息"):
            with st.form("edit_group_form"):
                name = st.text_input("Group 名称", value=group["name"])
                group_type = st.selectbox(
                    "Group 类型",
                    models.GROUP_TYPES,
                    index=models.GROUP_TYPES.index(group["group_type"])
                    if group.get("group_type") in models.GROUP_TYPES
                    else 0,
                )
                description = st.text_area("Group 描述", value=group.get("description") or "", height=100)
                submitted = st.form_submit_button("保存修改")
            if submitted:
                ok, message = models.update_group(group_id, user["id"], name, description, group_type)
                st.success(message) if ok else st.error(message)
                if ok:
                    rerun()

    st.subheader("成员列表")
    members = models.get_group_members(group_id)
    member_rows = [
        {"昵称": row["nickname"], "用户名": row["username"], "角色": "创建者" if row["role"] == "owner" else "成员"}
        for row in members
    ]
    st.dataframe(pd.DataFrame(member_rows), use_container_width=True)

    if is_owner:
        render_create_activity_form(group_id)

    pending = models.list_group_activities(group_id, "pending")
    confirmed = models.list_group_activities(group_id, "confirmed")

    st.subheader("待排期活动")
    if pending:
        for row in pending:
            render_activity_row(row, is_owner)
    else:
        st.info("暂无待排期活动。")

    st.subheader("已确认活动")
    if confirmed:
        for row in confirmed:
            render_activity_row(row, is_owner)
    else:
        st.info("暂无已确认活动。")


def render_create_activity_form(group_id: int) -> None:
    with st.expander("创建待排期活动"):
        with st.form("create_activity_form"):
            title = st.text_input("活动名称")
            description = st.text_area("活动说明", height=90)
            col1, col2 = st.columns(2)
            candidate_start = col1.date_input("候选开始日期", value=date.today())
            candidate_end = col2.date_input("候选结束日期", value=date.today())
            col3, col4 = st.columns(2)
            daily_start = col3.time_input("每日候选开始时间", value=time(19, 0))
            daily_end = col4.time_input("每日候选结束时间", value=time(22, 0))
            duration = st.number_input("活动时长（分钟）", min_value=15, max_value=480, value=60, step=15)
            location = st.text_input("地点")
            note = st.text_area("备注", height=80)
            submitted = st.form_submit_button("创建活动")
        if submitted:
            if candidate_start > candidate_end:
                st.error("候选开始日期不能晚于结束日期。")
            elif daily_start >= daily_end:
                st.error("每日候选开始时间必须早于结束时间。")
            elif not generate_candidate_slots(candidate_start, candidate_end, daily_start, daily_end, int(duration)):
                st.error("候选时间范围无法生成有效时间段。")
            else:
                ok, message, activity_id = models.create_activity(
                    group_id,
                    current_user()["id"],
                    title,
                    description,
                    candidate_start,
                    candidate_end,
                    daily_start,
                    daily_end,
                    int(duration),
                    location,
                    note,
                )
                st.success(message) if ok else st.error(message)
                if ok:
                    st.session_state.selected_activity_id = activity_id
                    st.session_state.page = "智能排期"
                    rerun()


def render_activity_row(row: dict, is_owner: bool) -> None:
    with st.container():
        col_main, col_schedule, col_delete = st.columns([5, 1, 1])
        status_text = "已确认" if row["status"] == "confirmed" else "待排期"
        tone = "green" if row["status"] == "confirmed" else "amber"
        col_main.markdown(f"**{row['title']}**  {tag(status_text, tone)}", unsafe_allow_html=True)
        col_main.caption(format_activity_time(row))
        if row.get("location"):
            col_main.write(f"地点：{row['location']}")
        if col_schedule.button("排期", key=f"schedule_activity_{row['id']}", use_container_width=True):
            st.session_state.selected_activity_id = row["id"]
            st.session_state.selected_group_id = row["group_id"]
            st.session_state.page = "智能排期"
            rerun()
        if is_owner and col_delete.button("删除", key=f"delete_activity_{row['id']}", use_container_width=True):
            ok, message = models.delete_activity(row["id"], current_user()["id"])
            st.success(message) if ok else st.error(message)
            rerun()
        st.divider()


def select_activity_when_missing() -> dict | None:
    user = current_user()
    activities = models.list_user_activities(user["id"])
    if not activities:
        st.info("你所在的 Group 里还没有活动。")
        return None

    selected = st.selectbox(
        "选择活动",
        activities,
        format_func=lambda row: f"{row['group_name']} / {row['title']} / {'已确认' if row['status'] == 'confirmed' else '待排期'}",
    )
    if st.button("进入活动排期", use_container_width=True):
        st.session_state.selected_activity_id = selected["id"]
        st.session_state.selected_group_id = selected["group_id"]
        rerun()
    return None


def build_recommendations(activity: dict) -> tuple[list[dict], list[dict]]:
    members = models.get_group_members(activity["group_id"])
    member_ids = [row["user_id"] for row in members]
    availability_rows = models.get_activity_availability(activity["id"])
    personal_events = models.get_personal_events_for_users(
        member_ids,
        activity["candidate_start_date"],
        activity["candidate_end_date"],
    )
    recommendations = compute_recommendations(activity, members, availability_rows, personal_events)
    return recommendations, members


def render_scheduling() -> None:
    user = current_user()
    st.title("智能排期")

    activity_id = st.session_state.get("selected_activity_id")
    if activity_id is None:
        select_activity_when_missing()
        return

    activity = models.get_activity(activity_id)
    if activity is None or models.get_member_role(activity["group_id"], user["id"]) is None:
        st.error("无法访问该活动。")
        st.session_state.selected_activity_id = None
        return

    is_owner = activity["owner_id"] == user["id"]
    st.subheader(activity["title"])
    st.caption(f"所属 Group：{activity['group_name']} · 状态：{'已确认' if activity['status'] == 'confirmed' else '待排期'}")
    st.write(activity.get("description") or "暂无活动说明。")
    st.markdown(
        f"{tag(format_activity_time(activity), 'green' if activity['status'] == 'confirmed' else 'amber')}",
        unsafe_allow_html=True,
    )
    if activity.get("location"):
        st.write(f"地点：{activity['location']}")

    slots = generate_candidate_slots(
        activity["candidate_start_date"],
        activity["candidate_end_date"],
        activity["daily_start_time"],
        activity["daily_end_time"],
        activity["duration_minutes"],
    )
    if not slots:
        st.error("该活动没有可用候选时间段。")
        return

    st.subheader("提交我的空闲时间")
    existing = models.get_user_availability(activity["id"], user["id"])
    existing_map = {
        (row["slot_start"], row["slot_end"]): row["status"]
        for row in existing
    }
    with st.form("availability_form"):
        choices = []
        for slot in slots:
            current_value = existing_map.get((slot["slot_start"], slot["slot_end"]), "maybe")
            label = STATUS_VALUE_TO_LABEL.get(current_value, "不确定")
            selected_label = st.selectbox(
                slot["label"],
                ["有空", "不确定", "没空"],
                index=["有空", "不确定", "没空"].index(label),
                key=f"slot_{activity['id']}_{slot['slot_start']}",
            )
            choices.append(
                {
                    "slot_start": slot["slot_start"],
                    "slot_end": slot["slot_end"],
                    "status": STATUS_LABEL_TO_VALUE[selected_label],
                }
            )
        submitted = st.form_submit_button("保存我的空闲时间", use_container_width=True)
    if submitted:
        models.save_availability(activity["id"], user["id"], choices)
        st.success("空闲时间已保存。")
        rerun()

    recommendations, members = build_recommendations(activity)
    st.subheader("智能推荐结果")
    st.caption(f"候选时间段 {len(slots)} 个，Group 成员 {len(members)} 人。")
    if recommendations:
        top = recommendations[0]
        st.success(
            f"推荐时间：{top['slot_label']}；综合得分：{top['score']}；"
            f"冲突人数：{top['conflict_count']}。{top['reason']}"
        )
        table = pd.DataFrame(recommendations)[
            [
                "slot_label",
                "score",
                "available_count",
                "maybe_count",
                "unavailable_count",
                "missing_count",
                "conflict_count",
                "conflict_members",
                "reason",
            ]
        ].rename(
            columns={
                "slot_label": "候选时间",
                "score": "综合得分",
                "available_count": "有空人数",
                "maybe_count": "不确定人数",
                "unavailable_count": "没空人数",
                "missing_count": "未提交人数",
                "conflict_count": "个人日程冲突人数",
                "conflict_members": "冲突成员",
                "reason": "推荐理由",
            }
        )
        st.dataframe(table, use_container_width=True)

        if is_owner and activity["status"] == "pending":
            st.subheader("确认最终活动时间")
            selected_index = st.selectbox(
                "选择要确认的时间段",
                range(len(recommendations)),
                format_func=lambda idx: (
                    f"{idx + 1}. {recommendations[idx]['slot_label']} · "
                    f"得分 {recommendations[idx]['score']} · "
                    f"冲突 {recommendations[idx]['conflict_count']} 人"
                ),
            )
            if st.button("确认活动并同步到成员个人日程", type="primary", use_container_width=True):
                selected = recommendations[selected_index]
                ok, message, _ = models.confirm_activity(
                    activity["id"],
                    user["id"],
                    selected["date"],
                    selected["start_time"],
                    selected["end_time"],
                )
                st.success(message) if ok else st.error(message)
                if ok:
                    rerun()
        elif activity["status"] == "confirmed":
            st.info("该活动已确认，并已同步到成员个人日程。")
        elif not is_owner:
            st.info("只有 Group 创建者可以确认最终活动时间。")
    else:
        st.info("暂无推荐结果。")


def render_settings() -> None:
    user = current_user()
    st.title("设置")

    with st.form("profile_form"):
        st.subheader("个人信息")
        st.text_input("用户名", value=user["username"], disabled=True)
        nickname = st.text_input("昵称", value=user["nickname"])
        submitted = st.form_submit_button("保存个人信息")
    if submitted:
        ok, message = models.update_user_profile(user["id"], nickname)
        st.success(message) if ok else st.error(message)
        if ok:
            refreshed = models.get_user_by_id(user["id"])
            if refreshed:
                st.session_state.user = refreshed
            rerun()

    with st.form("password_form"):
        st.subheader("修改密码")
        old_password = st.text_input("旧密码", type="password")
        new_password = st.text_input("新密码", type="password")
        submitted = st.form_submit_button("更新密码")
    if submitted:
        ok, message = auth.change_password(user["id"], old_password, new_password)
        st.success(message) if ok else st.error(message)


def main() -> None:
    st.set_page_config(page_title="MeetMate", page_icon="M", layout="wide")
    init_db()
    ensure_state()
    inject_global_styles()

    if not login_required():
        render_auth_page()
        return

    render_sidebar()
    page = st.session_state.page
    if page == "首页":
        render_home()
    elif page == "个人日程":
        render_personal_events()
    elif page == "我的 Group":
        render_groups()
    elif page == "Group 详情":
        render_group_detail()
    elif page == "智能排期":
        render_scheduling()
    elif page == "设置":
        render_settings()
    else:
        st.session_state.page = "首页"
        render_home()


if __name__ == "__main__":
    main()
