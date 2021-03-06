import json
import sys, os
import redis
import random, time, logging
from lazyupdredis import *
from threading import Thread
from time import sleep
from random import randint
sys.path.append("data/example_jsonbulk/")
import sample_generate
from redis.exceptions import ConnectionError


def do_get_or_set(cmds, t_num, num_setgets, key_range, args2, r, data):

    curr_data = data[0]
    for i in range(num_setgets):
        rand = str(random.randint(0, key_range-1))
        cmd = cmds[i]
        try:
            if cmd == 0:
                #print "GETTTT"
                r.get("key:" + rand)
            else:
                #print "SSSSSETTTT"
                r.set("key:" + rand, curr_data)
        except Exception:
            print "DISCONNECTED: count: " + str(i) + " thread:" + str(t_num)
            curr_data = data[1]
            r = lazyupdredis.connect(args2)
            print str(t_num) + " reconnected."

def do_get(args, unused, num_gets, key_range, args2, r, unused2):

    for i in range(num_gets):
        rand = str(random.randint(0, key_range-1))
        try:
            r.get("key:" + rand)
        except DeprecationWarning as e:
            r = lazyupdredis.connect(args2)

def do_set(args, unused, num_sets, key_range, args2, r, data):

    curr_data = data[0]
    for i in range(num_sets):
        rand = str(random.randint(0, key_range-1))
        try:
            r.set("key:" + rand, curr_data)
        except DeprecationWarning as e:
            print "DISCONNECTED: count: " + str(i) + " thread:" + str(t_num)
            curr_data = data[1]
            r = lazyupdredis.connect(args2)
            print str(t_num) + " reconnected."

def do_stats():
    actualredis = redis.StrictRedis()
    f = open('stats.txt', 'a')
    #f.write("Time\t#Queries\t#V0Keys\t#V1Keys\n")
    f.write("Time\t#Queries\t#V0Keys\n")
    i = 0
    while True:
        try:
            queries = actualredis.info()["instantaneous_ops_per_sec"]
            f.write(str(i) + "\t" + str(queries) + "\n")
            #f.write(str(len(actualredis.keys("ver0*"))) + "\n")
            #f.write(str(len(actualredis.keys("ver1*"))) + "\n")
            time.sleep(.5)
            i = i + .5
            #os.system("ps -ly `pidof redis-server` >> rss.txt")
        except ConnectionError:
            f.write("______________________________________________\n")
            f.flush()
            f.close()
            break
        

def bench(tname, fun_name, num_clients, num_funcalls, keyrange, args, args2, data, preload):
    """ 
    @param args: first set of args for lazyredis.
    @type args: list of tuples [("ns", "vers"), ...]
    @param args2: new set of args for lazyredis
    
    """

    print ">>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>  STARTING  " + tname + "  <<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<"

    client_handles = list()
    for tnum in range(num_clients): # must do ahead of time to not mess up timer
        r = lazyupdredis.connect(args)
        client_handles.append(r)
    cmds = list()
    for i in range(num_funcalls):
        cmds.append(random.randint(0, 1))

    # This thread prints the "queries per second"
    thread = (Thread(target=do_stats))
    thread.start()

    start = time.time()
    thread_arr = list()
    for t_num in range(num_clients):
        thread = (Thread(target = fun_name, args = (cmds, t_num, num_funcalls, keyrange, args2, client_handles[t_num], data)))
        thread_arr.append(thread)
        thread.start()


    sleep(20)

    updater = lazyupdredis.connect(args)
    # Version with a preload of module
    if preload is True:
        updater.do_upd("data/example_json/paper_dsl", "/tmp/mymodule.py")
    # Version with no pre-load of module
    elif preload is False:
        updater.do_upd("data/example_json/paper_dsl")
    print "UPDATE!!!!!!!"

    for t in thread_arr:
        print "joining: " + str(t)
        t.join()

    end = time.time()
    print ">>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>  SUCCESS  ("+tname+")  <<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<"
    return end - start

def start_redis(redis_loc):
    # also wipe out state persisted to disk
    #cmd = "rm dump.rdb"
    #os.system(cmd)
    #print "DB wiped from disk"
    logging.info("Starting redis ...\n")
    print (redis_loc +"redis-server " + redis_loc + "redis.conf 2>&1 &")
    os.system(redis_loc +"redis-server " + redis_loc + "redis.conf 2>&1 &")
    sleep(5)

def stop_redis():
    logging.info("Killing redis ...\n")
    cmd = "killall redis-server"
    os.system(cmd)
    sleep(5)



def lazy_cmd(redis_loc, cmd, preload):

    f = open('stats.txt', 'a')
    f.write(str(cmd) + "\t" + str(preload) + "\n")
    f.flush()
    f.close()

    num_keys = 200000    # the possible range of keys to iterate
    num_funcalls = 20000 # #gets in this case done over random keys (1 - num_keys)
    num_clients = 50

    start_redis(redis_loc)
    # non-hooked redis commands to work as orginally specified
    actualredis = redis.StrictRedis()

    val = {
    "_id": "4BD8AE97C47016442AF4A580",
    "customerid": 99999,
    "name": "Foo Sushi Inc",
    "since": "12/12/2012",
    "order": {
        "orderid": "UXWE-122012",
        "orderdate": "12/12/2001",
        "orderItems": [
            {
                "product": "Fortune Cookies",
                "price": 19.99
            }
        ]
    }}
    val2 = {
    "_id": "4BD8AE97C47016442AF4A580",
    "customerid": 99999,
    "name": "Foo Sushi Inc",
    "since": "12/12/2012",
    "order": {
        "orderid": "UXWE-122012",
        "orderdate": "12/12/2001",
        "orderItems": [
            {
                "product": "Fortune Cookies",
                "fullprice": 19.99,
                "price": 16.99
            }
        ]
    }}
    # prepopulate the DB
    #r = lazyupdredis.connect([("key", "ver0")])
    #for i in range(num_keys):
    #    r.set("key:" + str(i), json_val)
    #r = lazyupdredis.connect([("key", "ver0")])  
    #json_val = json.dumps(val)
    #num_keys = 20000           
    #for i in range(num_keys):                    
    #    r.set("key:" + str(i), json_val)  
    #r.save()     
    #sys.exit(0) 

    json_val = json.dumps(val)
    if cmd == "get":
        bench("lazy_redis_get_qps", do_get, num_clients,  num_funcalls, num_keys, [("key", "ver0")], [("key", "ver1")], None, preload)

    elif cmd == "set":
        json_val2 = json.dumps(val2)
        bench("lazy_redis_set_qps", do_set, num_clients,  num_funcalls, num_keys, [("key", "ver0")], [("key", "ver1")], [json_val, json_val2], preload)

    elif cmd == "getset":
        json_val2 = json.dumps(val2)
        bench("lazy_redis_getset_qps", do_get_or_set, num_clients,  num_funcalls, num_keys, [("key", "ver0")], [("key", "ver1")], [json_val, json_val2], preload)
    print str(len(actualredis.keys("ver0*"))) + " keys not updated, ",
    print str(len(actualredis.keys("ver1*"))) + " keys updated."
    print actualredis.info()
    print "There are " + str(len(actualredis.keys("*"))) + " total keys in redis "
    stop_redis()


def main():

#    logging.basicConfig(level=logging.DEBUG)

    # Remove the previous run's generated files, for sanity's sake.
    os.system("rm /tmp/gen*")
    redis_loc = "/fs/macdonald/ksaur/redis-2.8.19/src/"

    #for i in range(2):
    lazy_cmd(redis_loc, "getset", True)
    #lazy_cmd(redis_loc, "get", False)
    ##for i in range(11):
    #   lazy_cmd(redis_loc, "set", True)
    ##for i in range(11):
    #   lazy_cmd(redis_loc, "set", False)


if __name__ == '__main__':
    main()
