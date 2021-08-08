import sqlite3
import sys
import traceback
from typing import Dict, List, Tuple, Union

from utils import gen_code
from task import (
    get_all_tasks,
    get_task_by_id,
)

con = sqlite3.connect('database/sqlite.db')

sql_init = open('database/init.sql', 'r').read()
con.executescript(sql_init)
con.commit()

Code = str
Point = int
UsedBy = int
Error = Union[str, None]
CodePoint = Tuple[Code, Point, UsedBy]


def handle_error(err: sqlite3.Error) -> None:
    print(f'[-] SQLite error: {" ".join(err.args)}')
    print('[-] SQLite traceback: ')
    exc_type, exc_value, exc_tb = sys.exc_info()
    print(traceback.print_exception(exc_type, exc_value, exc_tb))


def gen_point_code(point: int = 0, amount: int = 1) -> Tuple[Union[List[str], None], Error]:
    sql = 'INSERT INTO `point_code`(`code`, `point`) VALUES (?, ?)'

    # keep trying until codes are unique
    while True:
        codes = [(gen_code(), point) for _ in range(amount)]

        try:
            con.executemany(sql, codes)
            con.commit()
            return ([code[0] for code in codes], None)

        except sqlite3.IntegrityError:
            con.rollback()
            continue

        except sqlite3.Error as err:
            handle_error(err)
            return (None, ' '.join(err.args))


def get_point_code() -> Tuple[Union[None, List[CodePoint]], Error]:
    sql = 'SELECT * FROM `point_code`'

    try:
        cur = con.execute(sql)
        rows = cur.fetchall()
        con.commit()
        return (rows, None)

    except sqlite3.Error as err:
        handle_error(err)
        return (None, ' '.join(err.args))


def use_point_code(code: str, group: int) -> Tuple[Union[Point, None], Error]:
    sql_check_not_used = 'SELECT `used_by`, `point` FROM `point_code` WHERE `code` = ?'
    sql_update = 'UPDATE `point_code` SET `used_by` = ? WHERE `code` = ?'

    try:
        cur = con.execute(sql_check_not_used, (code, ))
        res = cur.fetchone()
        con.commit()

        if res is None:
            return (None, 'not exists')

        used_by, point = res

        if used_by > 0 or used_by == -1:
            return (None, 'used')

        con.execute(sql_update, (group, code))
        con.commit()

        return (point, None)

    except sqlite3.Error as err:
        handle_error(err)
        return (None, ' '.join(err.args))


def delete_point_code(code: str) -> Tuple[None, Error]:
    sql_check_not_used = 'SELECT 1 FROM `point_code` WHERE `code` = ? AND `used_by` = 0'
    sql_delete = 'UPDATE `point_code` SET `used_by` = -1 WHERE `code` = ?'

    try:
        cur = con.execute(sql_check_not_used, (code, ))
        res = cur.fetchone()
        con.commit()

        if res is None:
            return (None, 'used')

        con.execute(sql_delete, (code, ))
        con.commit()

        return (None, None)

    except sqlite3.Error as err:
        handle_error(err)
        return (None, ' '.join(err.args))


def get_group_point() -> Tuple[Union[List[Tuple[int, int]], None], Error]:
    """
    Return a list of tuple where the `i`-th value is the rank `i+1`-th (group, point)

    e.g. if res[0] == (5, 100), then group 5 is currently at rank 1 with 100 points
    """

    sql = '''
        SELECT `used_by` AS `group`, SUM(`point`) AS `point`
        FROM `point_code`
        WHERE `used_by` > 0
        GROUP BY `used_by`
        ORDER BY `point` DESC, `group` ASC
    '''

    try:
        cur = con.execute(sql)
        rows = cur.fetchall()
        con.commit()

        res = []
        groups = set()
        for row in rows:
            res.append(row)
            groups.add(row[0])

        for i in range(1, 10):
            if i not in groups:
                res.append((i, 0))

        return (res, None)

    except sqlite3.Error as err:
        handle_error(err)
        return (None, ' '.join(err.args))


def get_group_selection_message_id() -> Tuple[Union[int, None], Error]:
    sql = 'SELECT `id` FROM `message` LIMIT 1'

    try:
        cur = con.execute(sql)
        row = cur.fetchone()
        con.commit()

        if row is None:
            return (None, 'not exists')

        return (row[0], None)

    except sqlite3.Error as err:
        handle_error(err)
        return (None, ' '.join(err.args))


def store_group_selection_message_id(id: int) -> Tuple[None, Error]:
    sql = 'INSERT INTO `message` VALUES (?)'

    try:
        con.execute(sql, (id, ))
        con.commit()

        return (None, None)

    except sqlite3.Error as err:
        handle_error(err)
        return (None, ' '.join(err.args))


def log_submission(
    group_id: int,
    task_id: str,
    password: str,
    is_correct: bool,
) -> Tuple[None, Error]:
    sql = '''
        INSERT INTO `submissions`(`group_id`, `task_id`, `password`, `is_correct`)
        VALUES (?, ?, ?, ?)
    '''

    try:
        con.execute(sql, (group_id, task_id, password, is_correct, ))
        con.commit()

        return (None, None)

    except sqlite3.Error as err:
        handle_error(err)
        return (None, ' '.join(err.args))


def get_submissions_statistics(
    group_id: int,
    task_id: str,
) -> Tuple[Union[None, Tuple[int, int]], Error]:
    sql = '''
        SELECT
            COALESCE(SUM(`is_correct` = 1), 0) AS `success_count`,
            COALESCE(SUM(`is_correct` = 0), 0) AS `fail_count`
        FROM `submissions`
        WHERE `group_id` = ? AND `task_id` = ?
    '''

    try:
        cur = con.execute(sql, (group_id, task_id, ))
        rows = cur.fetchone()
        con.commit()

        return (rows, None)

    except sqlite3.Error as err:
        handle_error(err)
        return (None, ' '.join(err.args))


def get_scoreboard() -> Tuple[Union[None, Dict[int, Dict[str, int]]], Error]:
    """
    Get scoreboard

    Returning a 2 dimensional dict
    where the value of result[group_id][task_id] is one of (-1, 0, 1)
    which means
        -1: running out of attemps,
        0: not yet solved,
        1: solved
    """
    sql = '''
        SELECT
            `group_id`,
            `task_id`,
            COALESCE(SUM(`is_correct` = 1), 0) AS `success_count`,
            COALESCE(SUM(`is_correct` = 0), 0) AS `fail_count`
        FROM `submissions`
        GROUP BY `group_id`, `task_id`
    '''

    try:
        cur = con.execute(sql)
        rows = cur.fetchall()
        con.commit()

        tasks = get_all_tasks()
        table = {i: {task['task_id']: 0 for task in tasks} for i in range(1, 10)}

        for row in rows:
            group_id, task_id, success_count, fail_count = row
            task = get_task_by_id(task_id)

            status = 0
            if 'max_attempt' in task and fail_count >= task['max_attempt']:
                status = -1
            elif success_count > 0:
                status = 1

            table[group_id][task_id] = status

        return (table, None)

    except sqlite3.Error as err:
        handle_error(err)
        return (None, ' '.join(err.args))
