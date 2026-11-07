/* GTK module scoped to the native keyboard and panel notification surfaces.
 * Keep overlays inside the circle without shrinking the desktop.
 * Uses the stable GLib/GTK C ABI; no private struct members or package patches.
 */
#include <stddef.h>
#include <string.h>
#include <dlfcn.h>
#include <unistd.h>
#include <stdio.h>
#include <time.h>
typedef unsigned long GType;
typedef unsigned int guint;
typedef int gboolean;
extern GType gtk_widget_get_type(void);
extern GType g_type_from_name(const char *);
extern void *g_type_class_ref(GType);
extern void g_type_class_unref(void *);
extern gboolean g_type_check_instance_is_a(void *, GType);
extern void *g_value_get_object(const void *);
extern guint g_signal_lookup(const char *, GType);
extern unsigned long g_signal_add_emission_hook(guint, guint,
    gboolean (*)(void *, guint, const void *, void *), void *, void *);
extern void g_object_set(void *, const char *, ...);
extern void g_object_get(void *, const char *, ...);
extern unsigned long g_signal_connect_data(void *, const char *, void (*)(void), void *, void *, int);
extern GType gtk_window_get_type(void);
extern GType gtk_label_get_type(void);
extern GType gtk_container_get_type(void);
extern void gtk_container_foreach(void *, void (*)(void *, void *), void *);
extern void *g_object_get_data(void *, const char *);
extern void g_object_set_data(void *, const char *, void *);
extern void gtk_widget_set_name(void *, const char *);
extern gboolean gtk_widget_get_visible(void *);
extern void gtk_window_get_size(void *, int *, int *);
typedef struct List { void *data; struct List *next, *prev; } List;
extern List *gtk_window_list_toplevels(void);
extern void g_list_free(List *);
extern guint g_timeout_add(guint, gboolean (*)(void *), void *);
extern const char *gtk_widget_get_name(void *);
extern const char *g_get_user_runtime_dir(void);
extern void gtk_widget_hide(void *);
extern void gtk_widget_show(void *);
extern void gtk_widget_queue_draw(void *);
extern void *gtk_widget_get_parent(void *);
extern char *gtk_widget_get_tooltip_text(void *);
extern void gtk_widget_set_no_show_all(void *, int);
extern GType gtk_button_get_type(void);
extern void *gtk_widget_get_toplevel(void *);
extern void g_free(void *);
extern void g_object_weak_ref(void *, void (*)(void *, void *), void *);

/* Launchpad already has a permanent launcher. Filter only its task button,
 * keeping the compositor handle available for activation and dock visibility.
 * wf-panel-pi sets task titles as tooltips after initially showing the button.
 */
static void filter_launchpad_task(void *button, void *property, void *unused)
{
    (void)property; (void)unused;
    char *title = gtk_widget_get_tooltip_text(button);
    int duplicate = g_object_get_data(button, "aroundos-top-launcher")
        ? strcmp(gtk_widget_get_name(button), "aroundos-launchpad.desktop") != 0
        : title && !strcmp(title, "Apps · AroundOS");
    g_free(title);
    if (property) gtk_widget_queue_draw(button);
    int filtered = g_object_get_data(button, "aroundos-filtered-task") != NULL;
    if (duplicate) {
        if (!filtered) {
            g_object_set_data(button, "aroundos-filtered-task", (void *)1);
            gtk_widget_set_no_show_all(button, 1);
        }
        if (gtk_widget_get_visible(button)) gtk_widget_hide(button);
    } else if (filtered) {
        g_object_set_data(button, "aroundos-filtered-task", NULL);
        gtk_widget_set_no_show_all(button, 0);
        gtk_widget_show(button);
    }
}

static void watch_task_button(void *widget)
{
    if (!g_type_check_instance_is_a(widget, gtk_button_get_type())) return;
    void *parent = gtk_widget_get_parent(widget);
    if (parent && !strcmp(gtk_widget_get_name(parent), "launchers")) {
        /* The native plugin shares [panel].launchers with the home dock.
         * Keep the full list there and limit only the top bar to Launchpad. */
        void *top = gtk_widget_get_toplevel(widget);
        if (!top || strcmp(gtk_widget_get_name(top), "PanelToplevel")) return;
        g_object_set_data(widget, "aroundos-top-launcher", (void *)1);
    } else {
        while (parent && strcmp(gtk_widget_get_name(parent), "window-list"))
            parent = gtk_widget_get_parent(parent);
        if (!parent) return;
    }
    if (!g_object_get_data(widget, "aroundos-task-watch")) {
        g_object_set_data(widget, "aroundos-task-watch", (void *)1);
        g_signal_connect_data(widget, "notify::tooltip-text",
            (void (*)(void))filter_launchpad_task, NULL, NULL, 0);
        g_signal_connect_data(widget, "notify::visible",
            (void (*)(void))filter_launchpad_task, NULL, NULL, 0);
    }
    filter_launchpad_task(widget, NULL, NULL);
}

extern void *gtk_window_new(int);
extern void gtk_window_set_decorated(void *, int);
extern void gtk_window_set_default_size(void *, int, int);
extern void *gtk_box_new(int, int);
extern void *gtk_label_new(const char *);
extern void gtk_label_set_text(void *, const char *);
extern void gtk_container_add(void *, void *);
extern void gtk_box_pack_start(void *, void *, int, int, unsigned int);
extern void gtk_widget_show_all(void *);
extern void *gtk_widget_get_screen(void *);
extern void *gdk_screen_get_rgba_visual(void *);
extern void gtk_widget_set_visual(void *, void *);
extern void *gtk_css_provider_new(void);
extern int gtk_css_provider_load_from_data(void *, const char *, long, void *);
extern void gtk_style_context_add_provider_for_screen(void *, void *, unsigned int);
extern void g_object_unref(void *);
static void *home_dock, *clock_window, *clock_time, *clock_date;
static gboolean update_clock(void *unused)
{
    (void)unused;
    time_t now = time(NULL);
    struct tm local;
    localtime_r(&now, &local);
    char text[128];
    strftime(text, sizeof(text), "%H:%M", &local);
    gtk_label_set_text(clock_time, text);
    strftime(text, sizeof(text), "%A, %d %B", &local);
    gtk_label_set_text(clock_date, text);
    return 1;
}
static void create_clock(void)
{
    if (clock_window) return;
    void (*init)(void *) = dlsym(RTLD_DEFAULT, "gtk_layer_init_for_window");
    void (*layer)(void *, int) = dlsym(RTLD_DEFAULT, "gtk_layer_set_layer");
    void (*zone)(void *, int) = dlsym(RTLD_DEFAULT, "gtk_layer_set_exclusive_zone");
    void (*name)(void *, const char *) = dlsym(RTLD_DEFAULT, "gtk_layer_set_namespace");
    if (!init || !layer || !zone || !name) return;
    clock_window = gtk_window_new(0);
    gtk_widget_set_name(clock_window, "aroundos-wallpaper-clock");
    gtk_window_set_decorated(clock_window, 0);
    gtk_window_set_default_size(clock_window, 520, 230);
    void *screen = gtk_widget_get_screen(clock_window);
    void *visual = gdk_screen_get_rgba_visual(screen);
    if (visual) gtk_widget_set_visual(clock_window, visual);
    init(clock_window); layer(clock_window, 1); zone(clock_window, 0);
    name(clock_window, "aroundos-clock");
    void *box = gtk_box_new(1, 4);
    g_object_set(box, "valign", 3, NULL);
    clock_time = gtk_label_new(""); clock_date = gtk_label_new("");
    gtk_widget_set_name(clock_time, "aroundos-clock-time");
    gtk_widget_set_name(clock_date, "aroundos-clock-date");
    gtk_box_pack_start(box, clock_time, 0, 0, 0);
    gtk_box_pack_start(box, clock_date, 0, 0, 0);
    gtk_container_add(clock_window, box);
    void *css = gtk_css_provider_new();
    gtk_css_provider_load_from_data(css,
        "#aroundos-wallpaper-clock {background:transparent;}"
        "#aroundos-clock-time {font:600 144px 'Rubik';color:#f5f5f7;}"
        "#aroundos-clock-date {font:28px 'Rubik';color:#a3ed75;}", -1, NULL);
    gtk_style_context_add_provider_for_screen(screen, css, 950);
    g_object_unref(css);
    update_clock(NULL); g_timeout_add(1000, update_clock, NULL);
    gtk_widget_show_all(clock_window);
}

static void clear_dock(void *data, void *object)
{
    (void)data; (void)object;
    home_dock = NULL;
}
static gboolean update_home_dock(void *unused)
{
    (void)unused;
    if (!home_dock) return 0;
    char path[512];
    snprintf(path, sizeof(path), "%s/aroundos-round-dock-hidden", g_get_user_runtime_dir());
    int hidden = access(path, F_OK) == 0;
    if (clock_window) {
        if (hidden && gtk_widget_get_visible(clock_window)) gtk_widget_hide(clock_window);
        if (!hidden && !gtk_widget_get_visible(clock_window)) gtk_widget_show(clock_window);
    }
    if (hidden && gtk_widget_get_visible(home_dock)) gtk_widget_hide(home_dock);
    if (!hidden && !gtk_widget_get_visible(home_dock)) gtk_widget_show(home_dock);
    return 1;
}

static guint layout_pending;

static gboolean position_notifications(void *unused)
{
    (void)unused;
    layout_pending = 0;
    const char *(*get_namespace)(void *) = dlsym(RTLD_DEFAULT, "gtk_layer_get_namespace");
    int (*get_margin)(void *, int) = dlsym(RTLD_DEFAULT, "gtk_layer_get_margin");
    void (*set_margin)(void *, int, int) = dlsym(RTLD_DEFAULT, "gtk_layer_set_margin");
    if (!get_namespace || !get_margin || !set_margin) return 0;
    void *windows[64];
    int count = 0;
    List *list = gtk_window_list_toplevels();
    for (List *item = list; item && count < 64; item = item->next) {
        if (g_object_get_data(item->data, "aroundos-inset") && gtk_widget_get_visible(item->data))
            windows[count++] = item->data;
    }
    g_list_free(list);
    for (int i = 1; i < count; i++) {
        void *window = windows[i];
        int j = i;
        while (j > 0 && get_margin(windows[j - 1], 2) > get_margin(window, 2)) {
            windows[j] = windows[j - 1];
            j--;
        }
        windows[j] = window;
    }
    int top = 250;
    for (int i = 0; i < count; i++) {
        int height = 0;
        gtk_window_get_size(windows[i], NULL, &height);
        if (get_margin(windows[i], 2) != top) set_margin(windows[i], 2, top);
        top += height + 12;
    }
    return 0;
}

static void schedule_notifications(void *window, void *allocation, void *unused)
{
    (void)window; (void)allocation; (void)unused;
    if (!layout_pending) layout_pending = g_timeout_add(100, position_notifications, NULL);
}

extern void cairo_save(void *);
extern void cairo_restore(void *);
extern void cairo_set_operator(void *, int);
extern void cairo_paint(void *);
extern void gtk_widget_set_app_paintable(void *, int);
extern void *gtk_widget_get_style_context(void *);
extern int gtk_widget_get_allocated_width(void *);
extern int gtk_widget_get_allocated_height(void *);
extern void gtk_render_background(void *, void *, double, double, double, double);
extern void gtk_render_frame(void *, void *, double, double, double, double);
static gboolean clear_notification(void *window, void *cr, void *unused)
{
    (void)unused;
    cairo_save(cr);
    cairo_set_operator(cr, 0); /* CAIRO_OPERATOR_CLEAR */
    cairo_paint(cr);
    cairo_restore(cr);
    void *style = gtk_widget_get_style_context(window);
    int width = gtk_widget_get_allocated_width(window);
    int height = gtk_widget_get_allocated_height(window);
    gtk_render_background(style, cr, 0, 0, width, height);
    gtk_render_frame(style, cr, 0, 0, width, height);
    return 0; /* GTK still paints the children. */
}

static void wrap_labels(void *widget, void *unused)
{
    (void)unused;
    if (g_type_check_instance_is_a(widget, gtk_label_get_type())) {
        g_object_set(widget, "max-width-chars", 42, "wrap", 1, "wrap-mode", 2, NULL);
    }
    if (g_type_check_instance_is_a(widget, gtk_container_get_type())) {
        gtk_container_foreach(widget, wrap_labels, NULL);
    }
}

static void floating_keyboard(void *window, void *property, void *unused)
{
    (void)property; (void)unused;
    int zone = 0;
    g_object_get(window, "exclusive-zone", &zone, NULL);
    if (zone) g_object_set(window, "exclusive-zone", 0, NULL);
}

#include "glass-bars.c"
#include "panel-cutouts.inc"
#include "shutdown-sheet.inc"
#include "recording-control.inc"

static gboolean inset_surfaces(void *hint, guint count, const void *values, void *data)
{
    (void)hint; (void)data;
    if (!count) return 1;
    void *window = g_value_get_object(values);
    if (window) {
        watch_task_button(window);
        watch_panel_image(window);
    }
    if (!window || !g_type_check_instance_is_a(window, gtk_window_get_type())) return 1;
    style_shutdown_sheet(window);
    glass_attach(window);
    recording_attach(window);
    if (!home_dock && !strcmp(gtk_widget_get_name(window), "DockToplevel")) {
        home_dock = window;
        create_clock();
        g_object_weak_ref(window, clear_dock, NULL);
        g_timeout_add(150, update_home_dock, NULL);
    }
    GType type = g_type_from_name("PhoshLayerSurface");
    if (window && type && g_type_check_instance_is_a(window, type)) {
        g_object_set(window, "margin-left", 150, "margin-right", 150,
            "margin-bottom", 200, "exclusive-zone", 0, NULL);
        if (!g_object_get_data(window, "aroundos-floating")) {
            g_object_set_data(window, "aroundos-floating", (void *)1);
            g_signal_connect_data(window, "notify::exclusive-zone",
                (void (*)(void))floating_keyboard, NULL, NULL, 0);
        }
    }
    /* These functions exist only in processes that already use gtk-layer-shell. */
    int (*is_layer)(void *) = dlsym(RTLD_DEFAULT, "gtk_layer_is_layer_window");
    const char *(*get_namespace)(void *) = dlsym(RTLD_DEFAULT, "gtk_layer_get_namespace");
    void (*set_anchor)(void *, int, int) = dlsym(RTLD_DEFAULT, "gtk_layer_set_anchor");
    int (*get_margin)(void *, int) = dlsym(RTLD_DEFAULT, "gtk_layer_get_margin");
    void (*set_margin)(void *, int, int) = dlsym(RTLD_DEFAULT, "gtk_layer_set_margin");
    if (is_layer && get_namespace && set_anchor && get_margin && set_margin && is_layer(window)) {
        const char *name = get_namespace(window);
        if (name && !strcmp(name, "notification") && !g_object_get_data(window, "aroundos-inset")) {
            g_object_set_data(window, "aroundos-inset", (void *)1);
            /* Rounded CSS corners need an alpha-capable backing surface.
             * The show hook runs before GTK realizes the notification. */
            void *visual = gdk_screen_get_rgba_visual(gtk_widget_get_screen(window));
            if (visual) gtk_widget_set_visual(window, visual);
            gtk_widget_set_app_paintable(window, 1);
            g_signal_connect_data(window, "draw", (void (*)(void))clear_notification, NULL, NULL, 0);
            wrap_labels(window, NULL);
            gtk_widget_set_name(window, "aroundos-notification");
            set_anchor(window, 0, 0); /* left */
            set_anchor(window, 1, 0); /* right: unanchor both to centre */
            set_margin(window, 1, 0);
            set_margin(window, 2, get_margin(window, 2) + 220);
            g_signal_connect_data(window, "size-allocate", (void (*)(void))schedule_notifications, NULL, NULL, 0);
            schedule_notifications(window, NULL, NULL);
        }
    }
    return 1;
}

void gtk_module_init(int *argc, char ***argv)
{
    (void)argc; (void)argv;
    GType widget_type = gtk_widget_get_type();
    void *widget_class = g_type_class_ref(widget_type);
    guint signal = g_signal_lookup("map", widget_type);
    if (signal) g_signal_add_emission_hook(signal, 0, inset_surfaces, NULL, NULL);
    signal = g_signal_lookup("show", widget_type);
    if (signal) g_signal_add_emission_hook(signal, 0, inset_surfaces, NULL, NULL);
    g_type_class_unref(widget_class);
}
