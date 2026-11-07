/* Restyle pishutdown's builder window, retaining its native action handlers. */
extern const char *g_get_prgname(void);
extern const char *gtk_buildable_get_name(void *);
extern void *gtk_button_new_with_label(const char *);
extern void gtk_box_set_spacing(void *, int);
extern void gtk_label_set_xalign(void *, float);
extern void gtk_window_close(void *);
extern void gtk_window_set_focus(void *, void *);
extern void gtk_container_set_border_width(void *, unsigned);

static void cancel_shutdown(void *button, void *window)
{
    (void)button;
    gtk_window_close(window);
}

static void identify_power_action(void *widget, void *unused)
{
    (void)unused;
    const char *id = gtk_buildable_get_name(widget);
    if (id && !strcmp(id, "btn_shutdown"))
        gtk_widget_set_name(widget, "shutdown-primary");
    if (id && !strcmp(id, "lbl_lock"))
        gtk_widget_set_name(widget, "shutdown-hint");
}

static void style_shutdown_sheet(void *window)
{
    const char *program = g_get_prgname();
    if (!program || strcmp(program, "pishutdown") ||
        g_object_get_data(window, "aroundos-shutdown-sheet")) return;
    const char *id = gtk_buildable_get_name(window);
    if (!id || strcmp(id, "main_window")) return;
    void *box = gtk_bin_get_child(window);
    if (!box || !g_type_check_instance_is_a(box, g_type_from_name("GtkBox"))) return;
    g_object_set_data(window, "aroundos-shutdown-sheet", (void *)1);
    gtk_container_foreach(box, identify_power_action, NULL);

    void *screen = gtk_widget_get_screen(window);
    void *visual = gdk_screen_get_rgba_visual(screen);
    if (visual) gtk_widget_set_visual(window, visual);
    gtk_window_set_decorated(window, 0);
    gtk_widget_set_name(window, "shutdown-sheet");
    gtk_container_set_border_width(window, 28);
    gtk_widget_set_size_request(window, 580, -1);
    gtk_box_set_spacing(box, 12);
    void *provider = gtk_css_provider_new();
    gtk_css_provider_load_from_data(provider,
        "#shutdown-sheet {background:#1c1c1f;color:#f5f5f7;border:1px solid #38383d;border-radius:32px;}"
        "#shutdown-sheet #shutdown-title {font:600 31px 'Rubik';color:#f5f5f7;margin-bottom:8px;}"
        "#shutdown-sheet button {min-height:56px;padding:0 14px;background:#29292e;color:#f5f5f7;"
        "font:21px 'Rubik';border:1px solid transparent;border-radius:16px;box-shadow:none;}"
        "#shutdown-sheet button:hover,#shutdown-sheet button:focus {border-color:#82828c;}"
        "#shutdown-sheet #shutdown-primary {background:#a3ed75;color:#182013;}"
        "#shutdown-sheet #shutdown-hint {font:17px 'Rubik';color:#b0b0ba;}", -1, NULL);
    gtk_style_context_add_provider_for_screen(screen, provider, 900);
    g_object_unref(provider);

    void *heading = gtk_label_new("Power options");
    gtk_label_set_xalign(heading, 0);
    gtk_widget_set_name(heading, "shutdown-title");
    gtk_box_pack_start(box, heading, 0, 1, 0);
    gtk_box_reorder_child(box, heading, 0);
    gtk_widget_show(heading);
    void *cancel = gtk_button_new_with_label("Cancel");
    gtk_box_pack_start(box, cancel, 0, 1, 0);
    gtk_box_reorder_child(box, cancel, 4);
    g_signal_connect_data(cancel, "clicked", (void (*)(void))cancel_shutdown, window, NULL, 0);
    gtk_widget_show(cancel);
    gtk_window_set_focus(window, cancel);
}
