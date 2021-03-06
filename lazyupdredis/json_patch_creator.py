'''

This is the main file for generating the update code.

Two modes: 
  1. generate a template to fill out from two (old and new) json test data files
  2. generate the python code to perform the update using the template file

Requires Python 2.7.
'''
import bisect, copy, sys, re, logging
import json
import decode
import argparse
import json_delta_diff
import ast
from pyparsing import nestedExpr


__VERSION__ = '0.3.1' # this version number refers to the DSL version


def generate_add_key(keyglob, usercode, outfile, prefix):
    """
    Generate code to add databasekeys.  Handles range nastiness.
    Ex: ea_n[1-2]@n[1-3,5] becomes ['ea_n1@n1', 'ea_n1@n2', ...'ea_n2@n5']

    @param keyglob: the limited keyglob of keys to add. (ranges but no wildcards)
    @param usercode: the code to initialize the new key 
    @type usercode: string
    @param outfile: the file to write the generated function to
    @param prefix: a string to ensure function name uniqueness
    @return: a dictionary of ( key blob command -> functions to call)
    """

    # Expand ranges, ex: [1-3,5] returns [1,2,3,5]
    # http://stackoverflow.com/questions/18759512/
    def mixrange(s):
        r = []
        for i in s.split(','):
            if '-' not in i:
                r.append(int(i))
            else:
                l,h = map(int, i.split('-'))
                r+= range(l,h+1)
        return r

    # TODO what did we decide the keywords are?
    patterns =  ['\\$dbkey\\s?=\\s?({.*})\\s?',
                '\\$outkey\\s?=\\s?({.*})\\s?']

    # get the value to initialize the keys to
    def extract_for_keys(estr):
        for p in patterns:
            cmd = re.match(p,estr)
            if cmd is not None:
                logging.debug( "outer Group 1  = " +  cmd.group(1))
                return cmd.group(1)
            else:
                sys.exit("No output command ($dbkey, $outkey) specified for dbkey" + keyglob)


    # remove weird chars from keyglob to use as function name
    funname = re.sub(r'\W+', '', str(prefix + keyglob))
    if "[" in keyglob:
        # use this library call to grab all the ranges (not actually nested)
        ranges = nestedExpr('[',']').parseString("[" + keyglob + "]").asList()[0]
        logging.debug("RANGES" + str(ranges) + " len " + str(len(ranges)))
        # We'll need nested appends for multiple ranges
        app = list()
        for r in ranges:
            logging.debug(  "r = " + str(r) + str(type(r)))
            # (ermm, it's not ideal to use type to see if it's a range or not...)
            # no range here, just apppend
            if type(r) is str:
                logging.debug( "STRRRR" + r)
                if len(app) == 0:
                    app.append(r)
                    logging.debug( "app" + str(app))
                else:
                    app = [x+r for x in app]
            # contains range.  loopy time.
            if type(r) is list:
                curr_range = mixrange(r[0])
                combo = list()
                # add new substrings to all existing substrings....yuck.
                for i in app:
                    for j in curr_range:
                        combo.append(str(i)+str(j))
                app = combo
        logging.debug(app)
    # not sure why anyone would use this update function to add a single key, but whatever
    else:
        app = list(keyglob)
      
    outfile.write("\ndef "+ funname + "():\n")
    tabstop = "    "
    #TODO additional tabstop?
    valstring = str(extract_for_keys(usercode))
    # Make sure the user provided a valid dictionary
    try:
        logging.debug( ast.literal_eval(valstring))  #str to dict
    except ValueError:
        sys.exit("You must provide a valid json string as a python dict: " + valstring)
    #barf. json to python and back ' vs " nastiness.
    #valstring = (cmd.replace("\"", "\\\"")).replace("\'", "\\\'")
    outfile.write(tabstop + "rediskeylist = " + str(app) + "\n")
    outfile.write(tabstop + "valstring = " + valstring + "\n")
    outfile.write(tabstop + "return (rediskeylist, valstring)\n")
    return [funname]

def generate_upd(cmddict, outfile, prefix):
    """
    Generate the update functions for each keyset.
    @param cmddict: a dictionary of commands mapped to regex (INIT, UPD, etc) 
    @param outfile: the file to write the generated function to
    @param prefix: a string to ensure function name uniqueness
    @return: a dictionary of ( key blob command -> functions to call)
    """
    function = ""
    getter = ""
    funname_list = list()
    for entry in cmddict:
        list_of_groups = cmddict.get(entry)
        for l in list_of_groups:
            # All commands will have group 1 (command) and group 2 (path)
            cmd =  l.group(1)
            keys = json.loads(l.group(2),object_hook=decode.decode_dict)
            usercode = ""
            newpath = ""
            # load usercode for INIT/UPD/DEL
            if (cmd == "INIT" or cmd == "UPD" or cmd == "DEL"):
                usercode = l.group(3)
            # load newpath if REN
            if (cmd == "REN"):
                newpath = json.loads(l.group(3),object_hook=decode.decode_dict) 
            if (entry != function):
                # write the function signature to file
                name = re.sub(r'\W+', '', str(prefix + entry))
                outfile.write("\ndef "+ name + "(rediskey, jsonobj):\n")
                # store the name of the function to call
                funname_list.insert(0, name)
                function = entry
                getter = ""

            # This next block prints the function sig/decls
            pos = 'e'  # for code generation.
                       # This is the first variable name and we'll increment it
            tabstop = "    "
            codeline = tabstop + pos + " = jsonobj"
            
            logging.debug(keys)
            if (len(keys) is 1 and type(keys[0]) is list):
                nextpos = chr(ord(pos) + 1) # increment the variable name
                codeline += "\n" +tabstop + "for " + nextpos +" in " + pos + ":"
                tabstop = tabstop + "    "
                pos = nextpos
            elif(len(keys)>0):
                for s in keys[0:(len(keys)-1)]:
                    logging.debug(type(s))
                    if (type(s) is not list):
                        codeline += ".get(\'" + s + "\')"
                    else: # arrays
                        # if array isn't the leaf
                        nextpos = chr(ord(pos) + 1) # increment the variable name
                        codeline += ".get(\'" + s[0] + "\')\n"
                        codeline += tabstop + "assert(" + pos + " is not None)\n"
                        codeline += tabstop + "for " + nextpos +" in " + pos + ":"
                        tabstop = tabstop + "    "
                        pos = nextpos
                        if (s != keys[(len(keys)-2)]):
                            nextpos = chr(ord(pos) + 1)
                            codeline += "\n" + tabstop + nextpos + " = " + pos
                            pos = nextpos
                        # TODO There are probably several scenarios this leaves out?
            if (getter != codeline):
                outfile.write(codeline+"\n")
                outfile.write(tabstop + "assert(" + pos + " is not None)\n")
                getter = codeline

            # Replace $out's with the variable to assign to
            if(len(keys)>0):
                logging.debug(type(keys[len(keys)-1]))
                if(type(keys[len(keys)-1]) is list):
                    vartoassign = pos+"[\'" + keys[len(keys)-1][0] + "\']"
                else:
                    vartoassign = pos+"[\'" + keys[len(keys)-1] + "\']"
            else:
                vartoassign = pos
            # whoa. where has this function been my whole life?
            if (cmd == "UPD"):
                outfile.write(tabstop + "tmp = " + vartoassign +"\n")
                usercode = usercode.replace("$in", "tmp") 
            if (cmd == "INIT" or cmd == "UPD" or cmd == "DEL"):
                usercode = usercode.replace("$out", vartoassign)
                usercode = usercode.replace("$base", pos)
                usercode = usercode.replace("$root", "jsonobj")
                usercode = usercode.replace("$dbkey", "rediskey")
            if (cmd == "INIT" or cmd == "UPD"):
                usercode = usercode.replace("|", "\n"+tabstop)
                outfile.write(tabstop + usercode+"\n")
            elif (cmd == "DEL"):  #TODO Implement DEL[]
                if(len(keys)==0):
                    keys.append("ALL_VALUES")
                usercodetabstop = tabstop +  "    "
                usercode = usercode.replace("|", "\n"+usercodetabstop)
                outfile.write(tabstop + "def test_del_" +(keys[len(keys)-1]) +"():\n")
                outfile.write(usercodetabstop + usercode+"\n")
                outfile.write(tabstop + "if test_del_" +(keys[len(keys)-1]) +"():\n")
                if (keys[0] != "ALL_VALUES"):
                    outfile.write(tabstop + "    del "+pos+"[\'" + (keys[len(keys)-1]) + "\']\n")
                else:
                    outfile.write(tabstop + "    rediskey = None\n")
            elif (cmd == "REN"):
                outfile.write(tabstop + pos+"[\'" + (newpath[len(newpath)-1]) + "\'] = "\
                + pos + ".pop("+ "\'" + (keys[len(keys)-1]) + "\'"     + ")\n")
        outfile.write("    return (rediskey, jsonobj)\n")
    return funname_list
             

def generate_dsltemplate(thediff, outfile):
    """
    Compute a diff and generate some stubs of INIT/DEL for the user to get started with
    """
    logging.debug(len(thediff))
    for l in thediff:
        assert(len(l) in (1,2))
        keys = l[0]
        assert(len(keys)>0)
        # adding
        if (len(l) == 2):
            outfile.write("INIT " +  (str(keys).replace("\'","\"")) + "\n")
        # deleting.
        else:
            # This writes local path only
            # outfile.write("DEL "+"[\'" + (keys[len(keys)-1]) + "\']\n")
            outfile.write("DEL "+ (str(keys).replace("\'","\"")) + "\n")


def parse_dslfile_inner(dslfile):
    """
    parses the inner portion of dsl funtions:
    {  .....(Rules beginning with INIT, UPD, REN, DEL).....}
    
    @return: a dictionary of rules that match the expected regular expressions
    """

    patterns =  ['(INIT)\\s+(\[.*\])\\s?\\s?\{(.*)\}',     #INIT [...] {...}
                 '(UPD)\\s+(\[.*\])\\s?\\s?\{(.*)\}',      #UPD [...] {...}
                 '(REN)\\s+(\[.*\])\\s?->\\s?(\[.*\])',     #REN [...]->[...]
                 '(DEL)\\s+(\[.*\])\\s?\\s?\{(.*)\}']       #DEL [...] {...}

    dsldict = dict()
    def extract_from_re(estr):
        for p in patterns:
            cmd = re.match(p,estr)
            if cmd is not None:
                return cmd
            else:
                logging.debug("FAIL")

    for line in dslfile:
        logging.debug("first line" + line)
        line = line.rstrip('\n')
        logging.debug("next line" + line)
        
        # parse multiline cmds. INIT and UPD and DEL have usercode, REN does not.
        if (("INIT" in line) or ("UPD" in line) or ("DEL" in line)): 
            while ("}" not in line):
                tmp = next(dslfile, None)
                if tmp is not None:
                    line += '|' + tmp.rstrip('\n')
                    logging.debug(line)
                else: # EOF
                    break
        logging.debug("=========================================\n\nline = " + line)
        curr = extract_from_re(line)
        if curr is not None:
            logging.debug("found " + str(len(curr.groups())) + " groups")
            logging.debug(curr.group(2))
            keys = json.loads(curr.group(2),object_hook=decode.decode_dict)
            #test for empty keys, meaning fullpath ([])
            if (len(keys) == 0):
                dsldict["ALL_VALUES"] = [curr] #TODO, better placeholder?
            elif (type(keys[0]) is list): #TODO other cases?? What if mid-list?  more testing needed.
                dsldict[keys[0][0]] = [curr]
            elif(keys[0] not in dsldict.keys()):
                dsldict[keys[0]] = [curr]
            else:
                dsldict[keys[0]].append(curr)
    logging.debug(dsldict)
    return dsldict

def parse_dslfile(dslfile, outfile):
    """
    Takes as input the DSL file in the format of: 
    for * {  .....(Rules beginning with INIT, UPD, REN, DEL).....}
    
    @return: a list of tuples (key:string (if any), commands:dictionary)
    """
    patterns =  ['(for namespace)\\s+(.*)->(.*)\\s+(.*)->(.*)\\s?{',
                 '(for) \\s?(\S*)\\s+(.*)->(.*)\\s?{',
                 '(add) \\s?(\S*)\\s+(.*)\\s?{']

    def extract_for_keys(estr):
        for p in patterns:
            cmd = re.match(p,estr)
            if cmd is not None:
                logging.debug("outer Group 2  = " +  cmd.group(2))
                return cmd
            else:
                logging.debug("FAIL (for/add)")

    tups = list() # for returning
    for line in dslfile:
        l = list() # list of all the readin dsl lines

        # Grab any imports the user may have included
        if line.startswith("import"):
            outfile.write(line)
            continue
      
        # skip blank lines in between "for key *{...};" stanzas
        if line == "\n":
            continue

        # get the "for/add ..." line,

        parsed = extract_for_keys(line)
        if parsed is None:
            sys.exit("\n\nFatal - Parse error near line containing: " + line)
        cmd = parsed.group(1)
        keyglob = parsed.group(2).strip()
        curr = next(dslfile, None)
        while curr and "};" not in curr:
            l.append(curr)
            curr = next(dslfile, None)
        # parse the stuff inside the "for" stanza
        if (cmd == "for"):
            inner = parse_dslfile_inner(iter(l))
            logging.debug("for INNER = " + str(inner))
            namespace = parse_namespace(keyglob)
            oldnamespace = namespace
            old_ver = parsed.group(3).strip()
            new_ver = parsed.group(4).strip()
        elif (cmd == "for namespace"):
            logging.debug("For Namespace match!")
            inner = parse_dslfile_inner(iter(l))
            oldnamespace = parsed.group(2)
            namespace = parsed.group(3)
            keyglob = namespace+"*"
            old_ver = parsed.group(4).strip()
            new_ver = parsed.group(5).strip()
        else: #guaranteed cmd == "add", else would have failed in 'extract'
            if "*" in keyglob or "?" in keyglob:
                sys.exit("\n\nFatal - Cannot use wildcards in keyglob for adding keys.\n")
            inner =  '|'.join(l)
            namespace = parse_namespace(keyglob)
            oldnamespace = None
            old_ver = None
            new_ver = parsed.group(3).strip()
        tups.append((cmd, keyglob, inner, oldnamespace, namespace, old_ver, new_ver))
        logging.debug("\n\ncmd: " + cmd)
        logging.debug("\n\nold_ver: " + str(old_ver))
        logging.debug("\n\nnew_ver: " + str(new_ver))
        logging.debug(tups)
    logging.info(tups)
    return tups

def parse_dslfile_string_only(dslfile_location):
    """
    Takes as input the name of a DSL file in the format of: 
    for * {  .....(Rules beginning with INIT, UPD, REN, DEL).....}

    Ignores the "adds", these will be done right way, not lazily, so no need to store.
    
    @param dslfile_location: The location of the DSL file for the update
    @type dslfile_location: string
    
    @return: a dictionary of {(oldver, newver, namespace) : [DSL String, ...], }
    """
    try:
       dslfile = open(dslfile_location, 'r')
    except IOError as e:
       logging.error("I/O error({0}): {1}".format(e.errno, e.strerror))
       return

    dsl_dict = dict() # for returning
    # Grab any imports the user may have included
    imp = list()
    line = dslfile.readline()
    while line.startswith("import"):
        imp.append(line)
        line = dslfile.readline()
    dslfile.seek(0)

    patterns =  ['(for namespace)\\s+(\S*)->(\S*)\\s+(\S*)->(\S*)\\s?{',
                 '(for) \\s?(\S*)\\s+(\S*)->(\S*)\\s?{']
    def extract_for_keys(estr):
        for p in patterns:
            cmd = re.match(p,estr)
            if cmd is not None:
                return cmd
            else:
                logging.debug("FAIL (for/add)")

    for line in dslfile:

        # skip blank lines in between "for key *{...};" stanzas
        if line == "\n":
           continue

        parsed = extract_for_keys(line)
        if parsed is None:
            continue
        l = list() # list of all the readin dsl lines
        l.append(line)
        cmd = parsed.group(1)
        curr = next(dslfile, None)
        while curr and "};" not in curr:
            l.append(curr)
            curr = next(dslfile, None)
        l.append(curr)
        l.insert(0,"\n".join(imp))
        if (cmd == "for"):
            keyglob = parsed.group(2).strip()
            namespace = parse_namespace(keyglob)
            oldns = namespace
            old_ver = parsed.group(3)
            new_ver = parsed.group(4)
        else:
            oldns = parsed.group(2)
            namespace = parsed.group(3)
            old_ver = parsed.group(4)
            new_ver = parsed.group(5)
        # parse the stuff inside the "for" stanza
        dict_key = (old_ver, new_ver, oldns, namespace)
        dsl_dict.setdefault(dict_key, []).extend(l)
    logging.debug(dsl_dict)
    return dsl_dict

def parse_namespace(name):
    """ split a key into namespace, return namespace if it exists, else * """
    if (":" not in name):
        logging.warning("WARNING: using default namespace (*) for \'" + name + "\'.")
        return "*"
    return name[0:name.rfind(":")]

def split_namespace_key(name):
    """ split a key into namespace and name, return as a tuple"""
    index = name.rfind(":")
    if index == -1:
        return ("*", name)
    return (name[0:index], name[index+1:])


def bulkload(f, jsonarr):
    for line in f:
        # A file may contain mulitple JSON objects with unknown size.
        # This code will load up all the JSON objects by reading from file
        # until one is successfully parsed.  Continuges until EOF.
        # http://stackoverflow.com/questions/20400818/
        while line is not None:
            try:
                jfile = json.loads(line,object_hook=decode.decode_dict)
                break
            except ValueError:
                # Not yet a complete JSON value
                tmp = next(f, None)
                if tmp is not None:
                    line +=tmp
                else: # EOF
                    break
        logging.debug("loaded:")
        logging.debug(jfile)
        jsonarr.append(jfile)


def make_template(file1, file2):
    """
    This function is the entry point for generating the template
  
    This function creates a file called "generated_dsl_init" from
    the diff of two json templates.

    @param file1: the original 'schema' sample json file
    @type file1: string
    @param file2: the new 'schema' sample json file
    @type file2: string
    """
    f1 = open(file1, 'r')
    f2 = open(file2, 'r')
    outfile = open("generated_dsl_init", 'w') #TODO params
    jsonarray1 = []
    jsonarray2 = []

    bulkload(f1, jsonarray1)
    bulkload(f2, jsonarray2)
    logging.debug("ARRRAY IS:" + str(jsonarray1))

    assert len(jsonarray1) == len(jsonarray2), \
     "Files should contain the same number of json templates..."

    for json1, json2 in zip(jsonarray1, jsonarray2):
        thediff = json_delta_diff.diff(json1, json2)
        logging.info("\nTHE DIFF IS: (len " + str(len(thediff)) + ")")
        logging.info(thediff)

    # generate the template file here
    generate_dsltemplate(thediff, outfile)


def process_dsl(file1, outfile="dsu.py"):
    """
    This function is the entry point for generating the update code.

    This function processes the dsl file and generates the update file "dsu.py"
    (or other name as specified) to update the json entries in the databse
    """

    # Open the init file
    dslfile = open(file1, 'r')

    # Open the output file
    outfile = open(outfile, 'w')

    # parse DSL file
    dsllist = parse_dslfile(dslfile, outfile)

    # create a list to store the parsed dsl output
    kv_update_pairs = list()
    kv_nschange_pairs = list()
    kv_new_pairs = list()

    # Generate the functions based on the DSL file contents
    # (Use the index as the namespace, as the keystring has too many special chars) 
    #
    # Tuples are in the format of: (cmd, keyglob, inner, namespace, old_ver, new_ver)
        ###tups.append((cmd, keyglob, inner, oldnamespace, namespace, old_ver, new_ver))
    for idx, curr_tup in enumerate(dsllist):
        if (curr_tup[0] == "for") or (curr_tup[0] == "for namespace"):
            kv_update_pairs.append((curr_tup[1], generate_upd(curr_tup[2], outfile, "group_"+str(idx)+"_update_"), curr_tup[3], curr_tup[4], curr_tup[5], curr_tup[6]))
        else:
            kv_new_pairs.append((curr_tup[1],  generate_add_key(curr_tup[1], curr_tup[2], outfile, "group_"+str(idx)+"_adder_"), curr_tup[4], curr_tup[6]))

    # write the name of the key globs and corresponding functions
    outfile.write("\ndef get_update_tuples():\n    return " + str(kv_update_pairs))
    outfile.write("\ndef get_newkey_tuples():\n    return " + str(kv_new_pairs))

    # cleanup
    outfile.close()
    dslfile.close()
         

def main():

    """
    To generate a template to fill out (containing the added/deleted fields between 2 json files):
  
    >>> python json_patch_creator.py --t ../tests/data/example_json/sample1.json ../tests/data/example_json/sample2.json

    To generate the update code from the template:

    >>> python json_patch_creator.py --d ../tests/data/example_json/sample_init

    """
    parser = argparse.ArgumentParser()
    parser.add_argument('--t', nargs=2, help='generate the template dsl file from 2 json template files')
    parser.add_argument('--d', nargs=1, help='process the dsl file and generate the update file')
    args = parser.parse_args()

    # Template option
    if (args.t) is not None:
        make_template(args.t[0], args.t[1])

    # Process DSL file option
    if (args.d) is not None:
        process_dsl(args.d[0])


if __name__ == '__main__':
    main()
