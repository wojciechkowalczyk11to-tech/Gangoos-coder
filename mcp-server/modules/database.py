"""
NEXUS MCP — Database Module
PostgreSQL, SQLite, Redis, MySQL
"""
import json
import logging
from typing import Optional
from pydantic import BaseModel, Field, ConfigDict
from mcp.server.fastmcp import FastMCP, Context

log = logging.getLogger("nexus-mcp.database")


def register(mcp: FastMCP):

    # ── PostgreSQL ───────────────────────────────────────

    class PGQueryInput(BaseModel):
        model_config = ConfigDict(extra="forbid")
        dsn: str = Field(..., description="PostgreSQL DSN, e.g. postgresql://user:pass@host:5432/db")
        query: str = Field(..., description="SQL query to execute")
        params: Optional[list] = Field(None, description="Query parameters (positional)")

    @mcp.tool(name="db_postgres_query", annotations={"title": "PostgreSQL Query"})
    async def db_postgres_query(params: PGQueryInput, ctx: Context) -> str:
        """Execute a SQL query on PostgreSQL and return results."""
        try:
            import psycopg2
            import psycopg2.extras
            conn = psycopg2.connect(params.dsn)
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cur.execute(params.query, params.params or [])
            if cur.description:
                rows = [dict(r) for r in cur.fetchmany(200)]
                result = {"rows": rows, "count": len(rows)}
            else:
                conn.commit()
                result = {"affected": cur.rowcount, "status": "ok"}
            cur.close()
            conn.close()
            return json.dumps(result, default=str)
        except ImportError:
            return "Error: psycopg2 not installed. Run: pip install psycopg2-binary"
        except Exception as e:
            return f"Error: {e}"

    # ── SQLite ───────────────────────────────────────────

    class SQLiteInput(BaseModel):
        model_config = ConfigDict(extra="forbid")
        db_path: str = Field(..., description="Path to SQLite database file")
        query: str = Field(..., description="SQL query to execute")
        params: Optional[list] = Field(None, description="Query parameters")

    @mcp.tool(name="db_sqlite_query", annotations={"title": "SQLite Query"})
    async def db_sqlite_query(params: SQLiteInput, ctx: Context) -> str:
        """Execute SQL query on a SQLite database."""
        try:
            import sqlite3
            conn = sqlite3.connect(params.db_path)
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            cur.execute(params.query, params.params or [])
            if cur.description:
                rows = [dict(r) for r in cur.fetchmany(200)]
                result = {"rows": rows, "count": len(rows)}
            else:
                conn.commit()
                result = {"affected": cur.rowcount, "status": "ok"}
            conn.close()
            return json.dumps(result, default=str)
        except Exception as e:
            return f"Error: {e}"

    class SQLiteSchemaInput(BaseModel):
        model_config = ConfigDict(extra="forbid")
        db_path: str = Field(..., description="Path to SQLite database file")

    @mcp.tool(name="db_sqlite_schema", annotations={"title": "SQLite Show Schema"})
    async def db_sqlite_schema(params: SQLiteSchemaInput, ctx: Context) -> str:
        """Show all tables and their schemas in a SQLite database."""
        try:
            import sqlite3
            conn = sqlite3.connect(params.db_path)
            cur = conn.cursor()
            cur.execute("SELECT name, sql FROM sqlite_master WHERE type='table'")
            tables = [{"name": r[0], "sql": r[1]} for r in cur.fetchall()]
            conn.close()
            return json.dumps({"tables": tables})
        except Exception as e:
            return f"Error: {e}"

    # ── Redis ────────────────────────────────────────────

    class RedisInput(BaseModel):
        model_config = ConfigDict(extra="forbid")
        host: str = Field("localhost", description="Redis host")
        port: int = Field(6379, description="Redis port")
        password: Optional[str] = Field(None, description="Redis password")
        db: int = Field(0, description="Redis database number")
        command: str = Field(..., description="Redis command, e.g. GET key, SET key value, KEYS *, HGETALL key")

    @mcp.tool(name="db_redis_cmd", annotations={"title": "Redis Command"})
    async def db_redis_cmd(params: RedisInput, ctx: Context) -> str:
        """Execute a Redis command."""
        try:
            import redis
            r = redis.Redis(host=params.host, port=params.port,
                            password=params.password, db=params.db, decode_responses=True)
            parts = params.command.split()
            cmd = parts[0].upper()
            args = parts[1:]
            result = r.execute_command(cmd, *args)
            if isinstance(result, (list, dict)):
                return json.dumps({"result": result})
            return json.dumps({"result": str(result)})
        except ImportError:
            return "Error: redis not installed. Run: pip install redis"
        except Exception as e:
            return f"Error: {e}"

    # ── MySQL ────────────────────────────────────────────

    class MySQLInput(BaseModel):
        model_config = ConfigDict(extra="forbid")
        host: str = Field(..., description="MySQL host")
        port: int = Field(3306, description="MySQL port")
        user: str = Field(..., description="MySQL user")
        password: str = Field(..., description="MySQL password")
        database: str = Field(..., description="Database name")
        query: str = Field(..., description="SQL query to execute")

    @mcp.tool(name="db_mysql_query", annotations={"title": "MySQL Query"})
    async def db_mysql_query(params: MySQLInput, ctx: Context) -> str:
        """Execute SQL query on MySQL database."""
        try:
            import pymysql
            import pymysql.cursors
            conn = pymysql.connect(
                host=params.host, port=params.port,
                user=params.user, password=params.password,
                database=params.database,
                cursorclass=pymysql.cursors.DictCursor,
            )
            with conn.cursor() as cur:
                cur.execute(params.query)
                if cur.description:
                    rows = cur.fetchmany(200)
                    result = {"rows": list(rows), "count": len(rows)}
                else:
                    conn.commit()
                    result = {"affected": cur.rowcount, "status": "ok"}
            conn.close()
            return json.dumps(result, default=str)
        except ImportError:
            return "Error: pymysql not installed. Run: pip install pymysql"
        except Exception as e:
            return f"Error: {e}"

    log.info("Database module registered (PostgreSQL, SQLite, Redis, MySQL)")
