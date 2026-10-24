import json
import sqlite3
from app.recognition_catalog import correct_literal, pin_tables


def catalog(path, names):
    with sqlite3.connect(path) as connection:
        connection.executescript('CREATE TABLE metadata(key TEXT,value TEXT);'
                                 "INSERT INTO metadata VALUES('complete','1');"
                                 'CREATE TABLE names(normalized TEXT,package INTEGER);'
                                 'CREATE TABLE packages(id INTEGER,source TEXT,name TEXT,pins TEXT,parent TEXT);')
        for name in names:
            connection.execute('INSERT INTO names VALUES(?,1)',(name.upper(),))


def test_spelling_requires_one_unique_full_library_name(tmp_path):
    path=tmp_path/'catalog.sqlite';catalog(path,['LM317_TO-220','Wio-SX1262'])
    assert correct_literal('LM317_T0-220',path)=='LM317_TO-220'
    assert correct_literal('Wio-SX1262',path)=='Wio-SX1262'
    assert correct_literal('NewPart345',path)=='NewPart345'
    with sqlite3.connect(path) as connection:
        connection.execute('INSERT INTO names VALUES(?,1)',('LM3I7_T0-220',))
    assert correct_literal('LM317_T0-220',path)=='LM317_T0-220'
    assert correct_literal('LM318_TO-220',path)=='LM318_TO-220'


def test_pin_inheritance_preserves_numbers_and_does_not_choose_packages(tmp_path):
    path=tmp_path/'catalog.sqlite';catalog(path,['Child'])
    with sqlite3.connect(path) as connection:
        connection.execute('INSERT INTO packages VALUES(1,?,?,?,?)',('source','Child',json.dumps({'2':['OUT']}),'Parent'))
        connection.execute('INSERT INTO packages VALUES(2,?,?,?,?)',('source','Parent',json.dumps({'1':['IN']}),None))
    assert pin_tables('Child',path)[0]['pins']=={'1':['IN'],'2':['OUT']}
    with sqlite3.connect(path) as connection:
        connection.execute("UPDATE metadata SET value='0'")
    assert not pin_tables('Child',path)
    assert correct_literal('Ch1ld',path)=='Ch1ld'
