import psycopg2
import os
from dotenv import load_dotenv

load_dotenv()

def analyze_tokens_categorized():
    try:
        pg_user = os.getenv('PG_USER', 'postgres')
        pg_password = os.getenv('PG_PASSWORD', 'admin')
        pg_host = os.getenv('PG_HOST', 'localhost')
        pg_port = os.getenv('PG_PORT', '5432')
        pg_database = os.getenv('PG_DATABASE', 'dbchat')
        
        print(f"Conectando a: {pg_host}:{pg_port}/{pg_database}")
        
        conn = psycopg2.connect(
            host=pg_host,
            port=pg_port,
            database=pg_database,
            user=pg_user,
            password=pg_password
        )
        cur = conn.cursor()
        
        print("=" * 60)
        print("ANÁLISE DETALHADA DOS TOKENS (NOVA CATEGORIZAÇÃO)")
        print("=" * 60)
        
        # Todos os threads
        cur.execute('SELECT thread_id, input_tokens, output_tokens FROM thread_tokens;')
        all_rows = cur.fetchall()
        print(f"\nTODOS OS THREADS ({len(all_rows)} registros):")
        for row in all_rows:
            thread_id = row[0]
            inp = row[1]
            out = row[2]
            is_plan = "PLANO" if thread_id.startswith("op_extract_") else "?"
            print(f"  {thread_id[:40]:<40} | In: {inp:>10,} | Out: {out:>8,} | {is_plan}")
        
        # PLANOS: threads em user_plans OU começando com op_extract_
        cur.execute("""
            SELECT 
                COALESCE(SUM(tt.input_tokens), 0) as total_input,
                COALESCE(SUM(tt.output_tokens), 0) as total_output,
                COUNT(DISTINCT tt.thread_id) as count
            FROM thread_tokens tt
            WHERE tt.thread_id IN (SELECT thread_id FROM user_plans)
               OR tt.thread_id LIKE 'op_extract_%';
        """)
        plan_stats = cur.fetchone()
        print(f"\n{'='*60}")
        print("TOKENS DE PLANOS (user_plans + op_extract_*)")
        print(f"  Threads: {plan_stats[2]}")
        print(f"  Total Input: {plan_stats[0]:,}")
        print(f"  Total Output: {plan_stats[1]:,}")
        if plan_stats[2] > 0:
            print(f"  Média Input/Plano: {plan_stats[0]//plan_stats[2]:,}")
            print(f"  Média Output/Plano: {plan_stats[1]//plan_stats[2]:,}")
        
        # CONVERSAS: excluindo planos e extrações
        cur.execute("""
            SELECT 
                COALESCE(SUM(input_tokens), 0) as total_input,
                COALESCE(SUM(output_tokens), 0) as total_output,
                COUNT(*) as count
            FROM thread_tokens tt
            WHERE tt.thread_id NOT IN (SELECT thread_id FROM user_plans)
              AND tt.thread_id NOT LIKE 'op_extract_%';
        """)
        conv_stats = cur.fetchone()
        print(f"\n{'='*60}")
        print("TOKENS DE CONVERSAS (excluindo planos e extrações)")
        print(f"  Threads: {conv_stats[2]}")
        print(f"  Total Input: {conv_stats[0]:,}")
        print(f"  Total Output: {conv_stats[1]:,}")
        if conv_stats[2] > 0:
            print(f"  Média Input/Conversa: {conv_stats[0]//conv_stats[2]:,}")
            print(f"  Média Output/Conversa: {conv_stats[1]//conv_stats[2]:,}")
        
        cur.close()
        conn.close()
        print("\n" + "=" * 60)
        print("Análise concluída!")
    except Exception as e:
        print(f"Erro: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    analyze_tokens_categorized()
