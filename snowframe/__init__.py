"""SnowFrame — notebook-native SQL workspace for Pandas DataFrames.

Quick start:
    from snowframe import SnowFrame, set_active_session

    sf = SnowFrame()
    sf.load({"sales": sales_df, "customers": customers_df})
    sf.sql("CREATE TABLE final AS SELECT * FROM sales WHERE amount > 1000")
    final_df = sf.to_df("final")

Notebook (after %load_ext snowframe):
    sf.auto()              # auto-register all DataFrames in scope
    set_active_session(sf) # activate %%sf / %%snowframe cell magic
"""

from snowframe.core import SnowFrame, SnowFrameError
from snowframe.magic import get_active_session, load_ipython_extension, set_active_session

__all__ = [
    "SnowFrame",
    "SnowFrameError",
    "set_active_session",
    "get_active_session",
    "load_ipython_extension",
]

__version__ = "0.1.0"
