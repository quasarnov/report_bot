from flask import Flask, render_template, request, redirect, url_for,session
from sqlalchemy import create_engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.engine import reflection
from sqlalchemy.sql import text
import os
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv() 

app = Flask(__name__)
app.secret_key = 'azerty95'

client = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY")
)

def connect_to_database(db_type, username, password, host, database):
    try:
        if db_type == 'MySQL':
            engine = create_engine(f'mysql+mysqlconnector://{username}:{password}@{host}/{database}')
        elif db_type == 'PostgreSQL':
            engine = create_engine(f'postgresql+psycopg2://{username}:{password}@{host}/{database}')
        else:
            return None, "Unsupported database type"
        connection = engine.connect()
        session['schema'] = get_database_schema(engine)
        
        return connection, None
    except SQLAlchemyError as e:
        return None, str(e)

def get_database_schema(engine):
    inspector = reflection.Inspector.from_engine(engine)
    schema_info = {}

    for table_name in inspector.get_table_names():
        columns = inspector.get_columns(table_name)
        foreign_keys = inspector.get_foreign_keys(table_name)
        schema_info[table_name] = {'columns': [], 'relationships': []}

        for column in columns:
            col_info = f"{column['name']} ({column['type']})"
            schema_info[table_name]['columns'].append(col_info)

        for fk in foreign_keys:
            rel_info = f"{fk['constrained_columns']} references {fk['referred_table']} ({fk['referred_columns']})"
            schema_info[table_name]['relationships'].append(rel_info)
    
    return schema_info


def format_schema_for_openai(schema_info):
    formatted_schema = "Database Schema:\n"
    for table, details in schema_info.items():
        formatted_schema += f"Table: {table}\n"
        formatted_schema += f" Columns: {', '.join(details['columns'])}\n"
        if details['relationships']:
            formatted_schema += f" Relationships: {', '.join(details['relationships'])}\n"
    return formatted_schema


def query_openai(prompt):
    try:
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": prompt}
            ]
        )
        return response.choices[0].message.content
    except Exception as e:
        return str(e)

@app.route('/', methods=['GET', 'POST'])
def home():
    if request.method == 'POST':
        db_type = request.form['db_type']
        host = request.form['host']
        username = request.form['username']
        password = request.form['password']
        database = request.form['database']
        connection, error = connect_to_database(db_type, username, password, host, database)
        if connection:
            schema_info = get_database_schema(connection)
            session['db'] = {'username':username,'password':password,'host':host,'database':database,'db_type':db_type}
            connection.close()
            # Pass the schema information to the template
            return render_template('schem.html', schema_info=schema_info)
        else:
            return f"Failed to connect: {error}"

    return render_template('index.html')

@app.route('/sql-query', methods=['GET', 'POST'])
def sql_query():
    if request.method == 'POST':
        user_query = request.form['query']
        formatted_schema = format_schema_for_openai(session['schema'])
        prompt = f"{formatted_schema}\nUser request: {user_query}\nSQL query:"

        # Generate SQL query using OpenAI
        generated_sql = query_openai(prompt)

        # The SQL query is sent to the template, but not executed yet
        return render_template('sql_query_result.html', sql_query=generated_sql)

    return render_template('sql_query_form.html')


@app.route('/execute-query', methods=['POST'])
def execute_query():
    sql_query = request.form['sql_query']
    print(sql_query)
    # Connect to the database
    connection, error = connect_to_database(session['db']['db_type'], session['db']['username'], session['db']['password'], session['db']['host'], session['db']['database'])

    try:
        # Execute the generated SQL query
        result = connection.execute(text(sql_query))
        
        # Check if it's a SELECT query and fetch results
        if sql_query.lower().startswith('select'):
            query_results = result.fetchall()
            columns = result.keys()
            return render_template('sql_query_result.html', sql_query=sql_query, rows=query_results, columns=columns)
        else:
            return render_template('sql_query_result.html', sql_query=sql_query, message="Query executed successfully.", rows=None, columns=None)

    except Exception as e:
        # Handle any errors that occur during SQL query execution
        return render_template('sql_query_result.html', sql_query=sql_query, error=str(e))

    finally:
        connection.close()


if __name__ == '__main__':
    app.run(debug=True)
