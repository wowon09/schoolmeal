from collections import defaultdict
from datetime import datetime, timedelta
import json
import re
from urllib.parse import urlencode
import urllib.request
from zoneinfo import ZoneInfo
import pandas as pd
import streamlit as st

# 페이지 기본 설정
st.set_page_config(page_title="학교 급식 찾아보기", page_icon="🍱", layout="centered")

st.title("🍱 학교 급식 찾아보기")


def normalize_school_name(name: str) -> list[str]:
    """축약어를 풀어 검색어 후보 생성"""
    names = [name.strip()]
    transformed = name.strip()

    if "여고" in transformed:
        transformed = transformed.replace("여고", "여자고등학교")
    elif transformed.endswith("고"):
        transformed = transformed[:-1] + "고등학교"
    elif "고" in transformed and not transformed.endswith("고등학교"):
        transformed = transformed.replace("고", "고등학교")

    if transformed != name.strip():
        names.append(transformed)

    return names


def fetch_json(url: str, params: dict) -> dict | None:
    """urllib를 사용한 API 호출 공통 함수"""
    query_string = urlencode(params)
    full_url = f"{url}?{query_string}"
    try:
        req = urllib.request.Request(full_url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=5) as response:
            if response.status == 200:
                return json.loads(response.read().decode("utf-8"))
    except Exception:
        return None
    return None


def fetch_school_info(school_name: str) -> list[dict]:
    """나이스 학교기본정보 API 호출"""
    url = "https://open.neis.go.kr/hub/schoolInfo"
    search_names = normalize_school_name(school_name)

    for search_term in search_names:
        params = {"Type": "json", "SCHUL_NM": search_term}
        data = fetch_json(url, params)
        if data and "schoolInfo" in data:
            rows = data["schoolInfo"][1]["row"]
            if rows:
                return rows
    return []


def fetch_meal_info(
    office_code: str, school_code: str, date_str: str
) -> dict | None:
    """하루 급식 정보 가져오기"""
    url = "https://open.neis.go.kr/hub/mealServiceDietInfo"
    params = {
        "Type": "json",
        "ATPT_OFCDC_SC_CODE": office_code,
        "SD_SCHUL_CODE": school_code,
        "MMEAL_SC_CODE": "2",  # 중식
        "MLSV_FROM_YMD": date_str,
        "MLSV_TO_YMD": date_str,
    }
    data = fetch_json(url, params)
    if data and "mealServiceDietInfo" in data:
        rows = data["mealServiceDietInfo"][1]["row"]
        if rows:
            return rows[0]
    return None


def fetch_period_meal_info(
    office_code: str, school_code: str, start_date: str, end_date: str
) -> list[dict]:
    """기간 내 급식 목록 가져오기"""
    url = "https://open.neis.go.kr/hub/mealServiceDietInfo"
    params = {
        "Type": "json",
        "ATPT_OFCDC_SC_CODE": office_code,
        "SD_SCHUL_CODE": school_code,
        "MMEAL_SC_CODE": "2",
        "MLSV_FROM_YMD": start_date,
        "MLSV_TO_YMD": end_date,
        "pSize": 100,
    }
    data = fetch_json(url, params)
    if data and "mealServiceDietInfo" in data:
        return data["mealServiceDietInfo"][1]["row"]
    return []


def extract_protein(ntr_info: str) -> float:
    """NTR_INFO에서 단백질(g) 수치 추출"""
    if not ntr_info:
        return 0.0
    match = re.search(r"단백질\(g\)\s*:\s*([\d.]+)", ntr_info)
    return float(match.group(1)) if match else 0.0


# 변수 초기화
selected_school = None

# 1. 학교 검색 섹션
st.subheader("1. 학교 검색")
input_school_name = st.text_input(
    "학교 이름을 입력하세요", placeholder="예: 수도여고, 송탄고, 서울중앙"
)

if input_school_name:
    schools = fetch_school_info(input_school_name)
    if not schools:
        st.warning("학교를 찾을 수 없습니다. 학교 이름을 다시 확인해 주세요.")
    else:
        school_options = {
            f"{s['SCHUL_NM']} ({s['LCTN_SC_NM']})": s for s in schools
        }
        selected_label = st.selectbox(
            "목록에서 학교를 선택하세요", options=list(school_options.keys())
        )
        selected_school = school_options[selected_label]

st.divider()

# 2. 날짜 선택 및 급식 메뉴 보기
st.subheader("2. 날짜 선택 및 급식 정보")

# 파이썬 기본 zoneinfo 모듈 사용 (한국 표준시)
korea_tz = ZoneInfo("Asia/Seoul")
today_korea = datetime.now(korea_tz).date()

selected_date = st.date_input("조회할 날짜를 선택하세요", value=today_korea)

if selected_school and selected_date:
    ymd_str = selected_date.strftime("%Y%m%d")
    meal_data = fetch_meal_info(
        selected_school["ATPT_OFCDC_SC_CODE"],
        selected_school["SD_SCHUL_CODE"],
        ymd_str,
    )

    st.subheader(
        f"📋 {selected_school['SCHUL_NM']} ({selected_date.strftime('%Y-%m-%d')}) 중식"
    )

    if meal_data:
        raw_dish_nm = meal_data.get("DDISH_NM", "")
        dishes = [dish.strip() for dish in raw_dish_nm.split("<br/>") if dish.strip()]

        st.markdown("#### 🥗 식단 메뉴")
        for dish in dishes:
            st.write(f"- {dish}")

        cal_info = meal_data.get("CAL_INFO", "정보 없음")
        st.info(f"🔥 **열량**: {cal_info}")
    else:
        st.info("해당 날짜에는 급식 정보가 없거나 제공되지 않습니다.")

    st.divider()

    # 3. 요일별 단백질 분석 섹션
    st.subheader("📊 요일별 단백질 분석")

    end_dt = today_korea
    start_dt = end_dt - timedelta(days=60)

    with st.spinner("최근 급식 영양 정보를 분석 중입니다..."):
        meals = fetch_period_meal_info(
            selected_school["ATPT_OFCDC_SC_CODE"],
            selected_school["SD_SCHUL_CODE"],
            start_dt.strftime("%Y%m%d"),
            end_dt.strftime("%Y%m%d"),
        )

    if meals:
        weekday_map = {0: "월요일", 1: "화요일", 2: "수요일", 3: "목요일", 4: "금요일"}
        protein_by_day = defaultdict(list)

        for meal in meals:
            ymd = meal.get("MLSV_YMD")
            ntr_info = meal.get("NTR_INFO", "")

            if ymd:
                dt = datetime.strptime(ymd, "%Y%m%d")
                weekday = dt.weekday()
                if weekday < 5:
                    protein = extract_protein(ntr_info)
                    if protein > 0:
                        protein_by_day[weekday_map[weekday]].append(protein)

        avg_protein = {}
        for day in ["월요일", "화요일", "수요일", "목요일", "금요일"]:
            values = protein_by_day.get(day, [])
            avg_protein[day] = round(sum(values) / len(values), 2) if values else 0.0

        df_protein = pd.DataFrame(
            list(avg_protein.items()), columns=["요일", "평균 단백질(g)"]
        )
        max_day = df_protein.loc[df_protein["평균 단백질(g)"].idxmax()]

        st.success(
            f"💡 최근 두 달간 분석 결과, 단백질이 가장 많은 요일은 **{max_day['요일']}** (평균 {max_day['평균 단백질(g)']}g) 입니다!"
        )
        st.bar_chart(data=df_protein.set_index("요일"))
    else:
        st.info("분석할 급식 데이터가 충분하지 않습니다.")

elif not selected_school:
    st.caption("👈 먼저 상단에서 학교를 검색하고 선택해 주세요.")
