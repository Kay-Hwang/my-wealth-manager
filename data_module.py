import os
import io
import base64
import pandas as pd
import streamlit as st

CSV_FILE = 'my_portfolio.csv'
COLUMNS = ['날짜', '티커', '거래종류', '단가', '수량', '통화', '적용환율', '계좌종류', '자산분류']

def is_cloud_env():
    """Streamlit Cloud의 secrets에 깃허브 토큰이 설정되어 있는지 확인"""
    try:
        return "GITHUB_TOKEN" in st.secrets and "GITHUB_REPO" in st.secrets
    except:
        return False

def get_github_repo():
    from github import Github
    g = Github(st.secrets["GITHUB_TOKEN"])
    repo = g.get_repo(st.secrets["GITHUB_REPO"])
    return repo

def init_csv():
    """CSV 파일이 없으면 초기 뼈대를 생성합니다."""
    if is_cloud_env():
        repo = get_github_repo()
        try:
            repo.get_contents(CSV_FILE)
        except:
            df = pd.DataFrame(columns=COLUMNS)
            csv_content = df.to_csv(index=False, encoding='utf-8-sig')
            repo.create_file(CSV_FILE, "Initialize portfolio CSV", csv_content)
    else:
        if not os.path.exists(CSV_FILE):
            df = pd.DataFrame(columns=COLUMNS)
            df.to_csv(CSV_FILE, index=False, encoding='utf-8-sig')
            print(f"'{CSV_FILE}' 파일이 생성되었습니다.")

def add_trade(date, ticker, trade_type, price, quantity, currency, exchange_rate, account_type, asset_cls):
    """새로운 거래 내역을 CSV에 추가합니다."""
    df = load_all_trades()
    new_data = pd.DataFrame([[date, ticker, trade_type, price, quantity, currency, exchange_rate, account_type, asset_cls]], columns=COLUMNS)
    df = pd.concat([df, new_data], ignore_index=True)
    save_all_trades(df)
    print("새로운 거래 내역이 추가되었습니다.")

def load_all_trades():
    """전체 CSV 데이터를 Pandas 데이터프레임으로 불러옵니다."""
    if is_cloud_env():
        try:
            repo = get_github_repo()
            contents = repo.get_contents(CSV_FILE)
            decoded = base64.b64decode(contents.content)
            df = pd.read_csv(io.BytesIO(decoded), encoding='utf-8-sig')
            return df
        except Exception as e:
            st.error(f"GitHub 데이터를 불러오지 못했습니다. (사유: {e})")
            init_csv()
            return pd.DataFrame(columns=COLUMNS)
    else:
        init_csv()
        df = pd.read_csv(CSV_FILE, encoding='utf-8-sig')
        return df

def save_all_trades(df):
    """수정된 전체 데이터프레임을 원격 데이터베이스(Github) 또는 로컬 CSV 파일로 저장합니다."""
    df.dropna(subset=['날짜'], inplace=True)
    csv_content = df.to_csv(index=False, encoding='utf-8-sig')
    
    if is_cloud_env():
        try:
            repo = get_github_repo()
            contents = repo.get_contents(CSV_FILE)
            repo.update_file(contents.path, "Update portfolio data via App", csv_content, contents.sha)
        except Exception as e:
            st.error(f"GitHub에 변경사항을 최신화하지 못했습니다. (사유: {e})")
    else:
        with open(CSV_FILE, 'w', encoding='utf-8-sig') as f:
            f.write(csv_content)

# ------------- 현재가 관리 기능 -------------
PRICE_FILE = 'current_prices.csv'
PRICE_COLUMNS = ['티커', '현재가']

def init_price_csv():
    if not os.path.exists(PRICE_FILE):
        df = pd.DataFrame(columns=PRICE_COLUMNS)
        df.to_csv(PRICE_FILE, index=False, encoding='utf-8-sig')

def save_current_prices(price_dict):
    """딕셔너리 형태의 {티커: 현재가}를 받아 CSV 파일 덮어쓰기로 저장합니다."""
    # 기존 데이터를 무시하고 덮어씁니다 (현재가만 필요하므로)
    records = [{'티커': k, '현재가': v} for k, v in price_dict.items()]
    df = pd.DataFrame(records, columns=PRICE_COLUMNS)
    df.to_csv(PRICE_FILE, index=False, encoding='utf-8-sig')

def load_current_prices():
    init_price_csv()
    df = pd.read_csv(PRICE_FILE, encoding='utf-8-sig')
    if df.empty:
        return {}
    # 딕셔너리로 변환하여 리턴
    return dict(zip(df['티커'], df['현재가']))
