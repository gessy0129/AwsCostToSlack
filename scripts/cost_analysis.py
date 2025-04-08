from logging import getLogger, INFO
import os
import datetime as dt
import boto3
import json
import pandas as pd
import matplotlib.pyplot as plt
import requests
import sys 
from botocore.exceptions import ClientError

logger = getLogger()
logger.setLevel(INFO)

def post_slack(data, start, end):
    # Slackにコストデータを投稿する
    file_name="aws_cost.png"
    file_data = open(data["GraphPath"], 'rb').read()
    files = {
        "file": (file_name, file_data, "image/png"),
    }
    data = {
        "token": os.environ.get("SLACK_APPLICATION_TOKEN"),
        "channels": os.environ.get("SLACK_CHANNEL_ID"),
        "filename": file_name,
        "filetype": "png",
        "initial_comment": f"アカウント名: {data['AccountName']} ({data['AccountId']}) \n{start} ~ {end} の料金\n直近7日間のトータルコスト${data['TotalCost']}"
    }

    post_message_url = "https://slack.com/api/files.upload"
    response = requests.post(
        post_message_url,
        data=data,
        files=files,
    )

    # レスポンスのステータスコードと内容をログに記録
    if response.status_code != 200:
        print(f"Error posting to Slack: {response.status_code}, {response.text}")
    else:
        print("Successfully posted to Slack")

def make_dataframe(cost_data):
    # AWS Cost Explorer の実行結果をpandaのdataframeの形式に加工する
    service_amount_template = {}

    for result in cost_data:
        for group in result['Groups']:
            for key in group['Keys']:
                if key not in service_amount_template.keys():
                    service_amount_template[key] = 0

    service_amount_template['Other'] = 0
    dataframe = {
        'Total': service_amount_template.copy()
    }

    for result in cost_data:
        start_date = result['TimePeriod']['Start']
        date = dt.datetime.strptime(start_date, '%Y-%m-%d').strftime('%-m/%-d')
        service_amount = service_amount_template.copy()

        # サービスごとにループ
        for group in result['Groups']:
            amount = round(float(group['Metrics']['AmortizedCost']['Amount']), 3)
            for key in group['Keys']:
                service_amount[key] = amount
                dataframe['Total'][key] += amount

        dataframe[date] = service_amount

    # 合計値が高い順にソートし、Top9を出す(残り1はOtherで合算)
    dataframe['Total'] = dict(sorted(dataframe['Total'].items(), key=lambda total: total[1], reverse=True))
    top_services = list(dataframe['Total'].keys())[0:9]

    for service in list(dataframe['Total'].keys()):
        if service not in top_services and service != 'Other':
            dataframe['Total']['Other'] += dataframe['Total'][service]
            dataframe['Total'].pop(service)

            for date in dataframe.keys():
                if date != 'Total':
                    dataframe[date]['Other'] += dataframe[date][service]
                    dataframe[date].pop(service)

    return pd.DataFrame(dataframe)

def save_bar(dataset, account_name, output_dir='/tmp'):
    # 積み上げ棒グラフ内にデータラベルを表示する
    # 合計値が大きい順にソート、グラフ表示時に合計値は要らないので除外
    dataset = dataset.sort_values(by='Total', ascending=False).drop('Total', axis=1)
    
    fig, ax = plt.subplots(figsize=(15, 8))
    
    # 積み上げ棒グラフの作成
    for i in range(len(dataset)):
        ax.bar(dataset.columns, dataset.iloc[i], bottom=dataset.iloc[:i].sum())
        for j in range(len(dataset.columns)):
            plt.text(x=j,
                y=dataset.iloc[:i, j].sum() + (dataset.iloc[i, j] / 2),
                s=round(dataset.iloc[i, j], 3),
                ha='center',
                va='bottom'
            )
    
    # グラフの設定
    ax.set_title(f'Daily Costs for Account: {account_name}')
    ax.set(xlabel='Date', ylabel='Cost ($)')
    ax.legend(dataset.index, bbox_to_anchor=(1.02, 1), loc='upper left', borderaxespad=0)
    
    plt.tight_layout()
    
    # アカウントごとのファイル名を設定
    img_path = os.path.join(output_dir, f'cost_{account_name.replace(" ", "_")}.png')
    fig.savefig(img_path, bbox_inches='tight')
    plt.close()  # メモリリーク防止のため、使用後にfigureを閉じる

    return img_path

def list_accounts():
    # Organizations APIからアカウント一覧を取得する
    try:
        org = boto3.client('organizations')
        paginator = org.get_paginator('list_accounts')
        accounts = []
            
        for page in paginator.paginate():
            for account in page['Accounts']:
                account_info = {
                    'AccountId': account['Id'],
                    'AccountName': account['Name'],
                    'AccountStatus': account['Status'],
                }
                accounts.append(account_info)
    except ClientError as err:
        logger.error(err.response['Error']['Message'])
        raise
    else:
        return accounts

def get_cost_json(account_id, start, end):
    # 特定のアカウントのコストを取得する
    ce = boto3.client('ce')
    response = ce.get_cost_and_usage(
        TimePeriod={
            'Start': start,
            'End': end,
        },
        Granularity='DAILY',
        Metrics=['AmortizedCost'],
        Filter={
            'Dimensions': {
                'Key': 'LINKED_ACCOUNT',
                'Values': [account_id]
            }
        },
        GroupBy=[
            {
                'Type': 'DIMENSION',
                'Key': 'SERVICE'
            }
        ]
    )
    return response['ResultsByTime']

def get_start_end_date():
    # 直近7日間の開始日、終了日を取得する
    now = dt.datetime.now()
    start = (now - dt.timedelta(days=8)).strftime('%Y-%m-%d')
    end = now.strftime('%Y-%m-%d')
    return [start, end]

def get_organization_costs():
    # Organization全体のコストを取得して分析する
    try:
        start, end = get_start_end_date()
        accounts = list_accounts()
        account_results = {}

        # Get account filter from environment variable, default to 'prod' if not set
        account_filter = os.environ.get("ACCOUNT_FILTER", "prod,stg,dev").split(",")
        logger.info(f"Filtering accounts by: {account_filter}")
        
        for account in accounts:
            # Check if any of the filter terms are in the account name
            if account['AccountStatus'] == 'ACTIVE' and any(filter_term.strip() in account['AccountName'] for filter_term in account_filter):
                account_id = account['AccountId']
                account_name = account['AccountName']
                try:
                    # アカウントごとのコストデータを取得
                    costs = get_cost_json(account_id, start, end)
                    
                    # コストデータをDataFrameに変換
                    df = make_dataframe(costs)
                    
                    # アカウントごとのグラフを作成
                    graph_path = save_bar(df, account_name)

                    # 結果を保存
                    account_results[account_id] = {
                        'AccountId': account_id,
                        'AccountName': account_name,
                        'Dataframe': df,
                        'GraphPath': graph_path,
                        'TotalCost': round(df['Total'].sum(), 2)
                    }
                    post_slack(account_results[account_id], start, end)                
                    
                    logger.info(f"Processed account {account_name} (ID: {account_id})")
                
                except Exception as err:
                    logger.error(f"Error processing account {account_id}: {err}")
                    account_results[account_id] = {
                        'AccountName': account_name,
                        'Error': str(err)
                    }
       
        return account_results
       
    except ClientError as e:
        logger.error(f"Error calling Organizations API: {e}")
        raise e

if __name__ == "__main__":
    error_count = 0  # エラーカウンター
    results = get_organization_costs()
    
    print("\nResults by account:")
    for account_id, result in results.items():
        if 'Error' in result:
            logger.error(f"\n{result['AccountName']} (ID: {account_id}):")
            logger.error(f"Error: {result['Error']}")
            error_count += 1  # エラーをカウント
        else:
            logger.info(f"\n{result['AccountName']} (ID: {account_id}):")
            logger.info(f"Total cost: ${result['TotalCost']:,.2f}")
            logger.info(f"Graph saved to: {result['GraphPath']}")

    if error_count > 0:
        logger.error("One or more accounts had errors during processing")
        sys.exit(1)
