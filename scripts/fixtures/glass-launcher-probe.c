/* Test-only LD_PRELOAD probe: intercept application launch and panel config save.
 * Never load this into the live panel. */
#include <stdio.h>
#include <stdlib.h>
static void record(const char *kind, const char *value)
{
    const char *path = getenv("GLASS_CHECK_EVENTS");
    if (!path) return;
    FILE *f = fopen(path, "a");
    if (f) { fprintf(f, "%s%s\n", kind, value); fclose(f); }
}
int g_app_info_launch(void *app, void *files, void *context, void *error)
{
    (void)app; (void)files; (void)context; (void)error;
    record("launch", ""); return 1;
}
void replace_launchers(const char *order) { record("save ", order); }
