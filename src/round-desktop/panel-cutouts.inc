/* The native window-list owns its buttons and updates their GtkImages.
 * Override only image drawing so theme refreshes, retitling and fallback
 * use the current native image, without changing any task interaction. */
extern void *g_file_new_for_path(const char *);
extern void *g_file_monitor_file(void *, int, void *, void *);
extern void *g_key_file_new(void);
extern int g_key_file_load_from_file(void *, const char *, int, void *);
extern char *g_key_file_get_string(void *, const char *, const char *, void *);
extern void g_key_file_unref(void *);
extern char *g_uri_escape_string(const char *, const char *, int);
extern void gdk_cairo_set_source_pixbuf(void *, void *, double, double);

static void reload_task_cutouts(void *monitor, void *file, void *other, int event, void *panel)
{
    (void)monitor; (void)file; (void)other; (void)event;
    const char *path = g_object_get_data(panel, "aroundos-task-map-path");
    void *map = g_key_file_new();
    g_key_file_load_from_file(map, path, 0, NULL);
    g_object_set_data_full(panel, "aroundos-task-map", map, g_key_file_unref);
    gtk_widget_queue_draw(panel);
}

static void watch_task_cutouts(void *panel)
{
    if (g_object_get_data(panel, "aroundos-task-map-path")) return;
    char *path = g_build_filename(g_get_user_runtime_dir(), "aroundos-round-task-icons.ini", (char *)NULL);
    g_object_set_data_full(panel, "aroundos-task-map-path", path, g_free);
    void *file = g_file_new_for_path(path);
    void *monitor = g_file_monitor_file(file, 0, NULL, NULL);
    g_object_unref(file);
    if (monitor) {
        g_signal_connect_data(monitor, "changed", (void (*)(void))reload_task_cutouts, panel, NULL, 0);
        g_object_set_data_full(panel, "aroundos-task-monitor", monitor, g_object_unref);
    }
    reload_task_cutouts(NULL, NULL, NULL, 0, panel);
}

static void *panel_cutout(void *panel, const char *stem)
{
    /* The watcher supplies a basename from its app ID table. */
    if (!stem || !*stem || strlen(stem) > 32 || strspn(stem, "abcdefghijklmnopqrstuvwxyz-") != strlen(stem))
        return NULL;
    char file[40], key[56];
    snprintf(file, sizeof(file), "%s.png", stem);
    snprintf(key, sizeof(key), "aroundos-panel-art-%s", stem);
    void *scaled = g_object_get_data(panel, key);
    if (!scaled) {
        /* The installer compiles from an absolute source path. A module built
         * in staging can also resolve the permanent installation on the Pi. */
        char *source = g_path_get_dirname(__FILE__);
        char *path = g_build_filename(source, "dock-icons", "cutouts", file, (char *)NULL);
        void *original = gdk_pixbuf_new_from_file(path, NULL);
        g_free(source); g_free(path);
        if (!original && getenv("HOME")) {
            path = g_build_filename(getenv("HOME"), "AroundOS", "src", "round-desktop",
                "dock-icons", "cutouts", file, (char *)NULL);
            original = gdk_pixbuf_new_from_file(path, NULL);
            g_free(path);
        }
        if (!original) return NULL;
        scaled = gdk_pixbuf_scale_simple(original, 32, 32, 2);
        g_object_unref(original);
        if (scaled) g_object_set_data_full(panel, key, scaled, g_object_unref);
    }
    return scaled;
}

static int draw_panel_cutout(void *image, void *cr, void *button)
{
    void *panel = gtk_widget_get_toplevel(image);
    void *map = g_object_get_data(panel, "aroundos-task-map");
    if (!map) return 0;
    void *art = NULL;
    if (!strcmp(gtk_widget_get_name(button), "aroundos-launchpad.desktop")) {
        art = panel_cutout(panel, "launchpad");
    } else {
        char *title = gtk_widget_get_tooltip_text(button);
        if (!title || !*title) { g_free(title); return 0; }
        char *key = g_uri_escape_string(title, NULL, 0);
        char *stem = g_key_file_get_string(map, "icons", key, NULL);
        art = panel_cutout(panel, stem);
        g_free(stem); g_free(key); g_free(title);
    }
    if (!art) return 0; /* Delegate Utilities and unknown titles to GTK. */
    gdk_cairo_set_source_pixbuf(cr, art, (gtk_widget_get_allocated_width(image) - 32) / 2,
        (gtk_widget_get_allocated_height(image) - 32) / 2);
    cairo_paint(cr);
    return 1;
}

static void watch_panel_image(void *image)
{
    if (!g_type_check_instance_is_a(image, gtk_image_get_type()) ||
        g_object_get_data(image, "aroundos-panel-image")) return;
    void *panel = gtk_widget_get_toplevel(image);
    if (strcmp(gtk_widget_get_name(panel), "PanelToplevel")) return;
    void *button = gtk_widget_get_parent(image);
    while (button && !g_type_check_instance_is_a(button, gtk_button_get_type()))
        button = gtk_widget_get_parent(button);
    if (!button) return;
    void *parent = gtk_widget_get_parent(button);
    if (!parent) return;
    if (!strcmp(gtk_widget_get_name(parent), "launchers")) {
        if (strcmp(gtk_widget_get_name(button), "aroundos-launchpad.desktop")) return;
    } else {
        while (parent && strcmp(gtk_widget_get_name(parent), "window-list"))
            parent = gtk_widget_get_parent(parent);
        if (!parent) return;
    }
    watch_task_cutouts(panel);
    g_object_set_data(image, "aroundos-panel-image", (void *)1);
    g_signal_connect_data(image, "draw", (void (*)(void))draw_panel_cutout, button, NULL, 0);
}
