#ifndef _KVOLVE_H
#define _KVOLVE_H
#include <bits/siginfo.h> // For redis.h 'siginfo_t' TODO why will this not work with signal.h??
#include "uthash.h"
#include "redis.h"


#define DEBUG
#ifdef DEBUG
# define DEBUG_PRINT(x) printf x
#else
# define DEBUG_PRINT(x) do {} while (0)
#endif

struct version_hash{
    char * ns; /* key */
    char ** versions; 
    int num_versions;
    UT_hash_handle hh; /* makes this structure hashable */
};

struct version_hash * version_hash_lookup(char * lookup);
int kvolve_process_command(redisClient *c);
int kvolve_append_version(char * vers_str);
void kvolve_set(redisClient * c);
void kvolve_get(redisClient * c);

#endif
