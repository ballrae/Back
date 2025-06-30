from airflow import DAG
from airflow.operators.bash import BashOperator
from datetime import datetime, timedelta

default_args = {
    'owner': 'yubin',
    'retries': 1,
    'retry_delay': timedelta(minutes=1),
}

with DAG(
    dag_id='run_producer_every_minute',
    default_args=default_args,
    description='Kafka producer 실행 DAG',
    # schedule_interval='30 18 * * 1-5',  # 월-금 18시 30분마다 실행
    schedule_interval='@once',
    start_date=datetime(2025, 6, 19),
    catchup=False,
) as dag:
    
    run_producer = BashOperator(
        task_id='run_producer',
        bash_command='docker start ballrae-kafka-producer'
    )