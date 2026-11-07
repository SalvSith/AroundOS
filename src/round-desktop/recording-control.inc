/* Recording state belongs to the persistent controller; the panel only displays it. */
#include <signal.h>
extern void cairo_fill(void *);
extern const char *g_get_home_dir(void);
extern void *gtk_button_new(void);
extern void gtk_widget_set_tooltip_text(void *, const char *);
extern List *gtk_container_get_children(void *);
static void *recording_dot;
static int recording_lit;
static int recording_saving;

static void recording_dot_destroyed(void *unused, void *object)
{
    (void)unused; (void)object;
    recording_dot = NULL;
}

static void recording_panel_destroyed(void *data, void *object)
{
    (void)object;
    *(void **)data = NULL;
}

static int recording_draw(void *widget, void *cr, void *unused)
{
    (void)unused;
    double x = gtk_widget_get_allocated_width(widget) / 2.0;
    double y = gtk_widget_get_allocated_height(widget) / 2.0;
    cairo_set_source_rgba(cr, 1.0, recording_saving ? 0.70 : 0.22,
                         recording_saving ? 0.15 : 0.27, recording_lit ? 1.0 : 0.30);
    cairo_arc(cr, x, y, 7.0, 0, 6.28318530718);
    cairo_fill(cr);
    return 1;
}

static void recording_clicked(void *button, void *unused)
{
    (void)button; (void)unused;
    char path[1024];
    snprintf(path, sizeof(path), "%s/.local/state/aroundos-round/recording.pid", g_get_home_dir());
    FILE *file = fopen(path, "r");
    long pid = 0;
    if (file) { if (fscanf(file, "%ld", &pid) != 1) pid = 0; fclose(file); }
    if (pid > 1) kill((pid_t)pid, SIGUSR2);
}

static void recording_find_clock(void *widget, void *unused)
{
    (void)unused;
    if (recording_dot) return;
    if (!strcmp(gtk_widget_get_name(widget), "clock")) {
        void *parent = gtk_widget_get_parent(widget);
        if (parent && g_type_check_instance_is_a(parent, g_type_from_name("GtkBox"))) {
            int index = 0;
            List *children = gtk_container_get_children(parent);
            for (List *p = children; p && p->data != widget; p = p->next) index++;
            g_list_free(children);
            recording_dot = gtk_button_new();
            g_object_weak_ref(recording_dot, recording_dot_destroyed, NULL);
            gtk_widget_set_name(recording_dot, "aroundos-recording-dot");
            gtk_widget_set_size_request(recording_dot, 44, 44);
            gtk_widget_set_tooltip_text(recording_dot, "Screen recording");
            gtk_widget_set_no_show_all(recording_dot, 1);
            g_signal_connect_data(recording_dot, "draw", (void (*)(void))recording_draw, NULL, NULL, 0);
            g_signal_connect_data(recording_dot, "clicked", (void (*)(void))recording_clicked, NULL, NULL, 0);
            gtk_box_pack_start(parent, recording_dot, 0, 0, 0);
            gtk_box_reorder_child(parent, recording_dot, index);
            char ready[1024];
            snprintf(ready, sizeof(ready), "%s/.local/state/aroundos-round/recording-panel.pid", g_get_home_dir());
            FILE *file = fopen(ready, "w");
            if (file) { fprintf(file, "%ld\n", (long)getpid()); fclose(file); }
            return;
        }
    }
    if (g_type_check_instance_is_a(widget, gtk_container_get_type()))
        gtk_container_foreach(widget, recording_find_clock, NULL);
}

static int recording_tick(void *data)
{
    void *window = *(void **)data;
    if (!window) { free(data); return 0; }
    if (!recording_dot) recording_find_clock(window, NULL);
    if (!recording_dot) return 1;
    char path[1024], state[32] = "";
    snprintf(path, sizeof(path), "%s/.local/state/aroundos-round/recording.status", g_get_home_dir());
    FILE *file = fopen(path, "r");
    if (file) { if (!fgets(state, sizeof(state), file)) state[0] = 0; fclose(file); }
    int active = !strcmp(state, "recording\n");
    recording_saving = !strcmp(state, "saving\n") || !strcmp(state, "stopping\n");
    if (active || recording_saving) {
        gtk_widget_set_tooltip_text(recording_dot, recording_saving ? "Saving screen recording…" : "Screen recording");
        recording_lit = !recording_lit;
        gtk_widget_show(recording_dot);
        gtk_widget_queue_draw(recording_dot);
    } else if (gtk_widget_get_visible(recording_dot)) gtk_widget_hide(recording_dot);
    return 1;
}

static void recording_attach(void *window)
{
    if (strcmp(gtk_widget_get_name(window), "PanelToplevel") ||
        g_object_get_data(window, "aroundos-recording-control")) return;
    g_object_set_data(window, "aroundos-recording-control", (void *)1);
    void **holder = malloc(sizeof(void *));
    *holder = window;
    g_object_weak_ref(window, recording_panel_destroyed, holder);
    g_timeout_add(500, recording_tick, holder);
}
