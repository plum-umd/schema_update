"""
Call all of the generated functions for the specified key stanzas 
in the redis database...now, not lazy.

Usage: python doupd.py

"""
import sys
import json
import decode
import redis
import sys
sys.path.append("../generated")
import redis

def connect(host=None, port=None):
    """ 
    Connect to redis. Default is localhost, port 6379.
    (Redis must be running.)

    @param host: the address of redis, defaults to 'localhost
    @param port: the port for redis, defaults to 6379
        
    """
    if host is None:
        host = 'localhost'
    if port is None:
        port = 6379
    r = redis.StrictRedis(host, port, db=0)
    try:
        r.ping()
    except r.ConnectionError as e:
        print(e)
        sys.exit(-1)
    return r

# TODO...redis objects
        ## For later, when it's not just strings...
        #redisval = None
        #typ = r.type(currkey)
        #print "key (" + typ + "): " + currkey
        #if typ == 'string':
        #    redisval = r.get(currkey)
        #### For later, when it's not just strings...
        #elif typ == 'hash':
        #    print r.hgetall(key)
        #elif typ == 'zset':
        #    print r.zrange(key, 0, -1)
        #elif typ == 'set':
        #    print r.smembers(key)
        #elif typ == 'list':
        #    print r.lrange(key, 0, -1)
        #print "---"


def do_upd_all_now(r, updfile="dsu"):
    """
    Perform the update.

    @param r: The instance of redis to update (already connected)
    @type updfile: string
    @param updfile: The file with the update functions.  Defaults to "dsu".
    @return: the number of keys updated
    
    """
    #strip off extention, if provided
    updfile = updfile.replace(".py", "")
    # load up the file to get all functions (like dlsym with Kitsune)
    print "importing from " + updfile
    m = __import__ (updfile)

    # handle the new/"add" cases
    get_newkey_tuples = getattr(m, "get_newkey_tuples")
    newkey_pairs = get_newkey_tuples()
    for (glob, funcs) in newkey_pairs:
        try:
            func = getattr(m,funcs[0])
        except AttributeError as e:
            print "(Could not find function: " + funcs[0] + ")"
            continue
        # retrieve the list of keys to add, and the usercode to set it to
        (keys, userjson) = func()
        for k in keys:
            r.set(k,json.dumps(userjson))

    # handle the update/"for" cases
    get_update_tuples = getattr(m, "get_update_tuples")
    update_pairs = get_update_tuples()
    print update_pairs
    print len(update_pairs)

    num_upd = 0
    # Loop over the "for/add __  " glob stanzas
    for (glob, funcs) in update_pairs:
        print "GLOB = " + glob
        print "FUNCS = " + str(funcs)
        keys = r.keys(glob)
        print "Printing \'" + str(len(keys)) + "\' keys:"
        # Loop over the keys matching the current glob
        for currkey in keys:
            redisval = None
            print "key: " + currkey
            redisval = r.get(currkey)
            print "value: |" + redisval + "|"

            # Make sure everything is loaded
            assert redisval is not None, ("could not find value for" + currkey)
            print type(redisval)
            jsonkey = json.loads(redisval, object_hook=decode.decode_dict)
            
            # Loop over the set of functions that apply to the keys
            for funcname in funcs:
                try:
                    func = getattr(m,funcname)
                except AttributeError as e:
                    print "(Could not find function: " + funcname + ")"
                    continue
                # Call the function for the current key and current jsonsubkey
                (modkey, modjson) = func(currkey, jsonkey)
                print "GOT BACK: " + str(modkey) + " " + str(modjson)

                # Now serialize it back, then write it back to redis.  
                # (Note that the key was modified in place.)
                modjsonstr = json.dumps(modjson)
                if(modkey is not None):
                    r.set(modkey, modjsonstr)
                # if key changed, delete the old
                if(modkey != currkey):
                    r.delete(currkey)
                num_upd+=1 

    return num_upd


def main():
    r = connect()
    do_upd_all_now(r)
            

if __name__ == '__main__':
    main()