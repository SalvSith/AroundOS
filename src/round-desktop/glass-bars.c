/* Native GTK panel treatment: concentric glass arcs and a magnifying home dock.
 * Included by surface-insets.c; keeps the original widgets and event handlers. */
#include <math.h>
#include <stdlib.h>
#include <strings.h>
#include <ifaddrs.h>
#include <arpa/inet.h>

typedef struct { int x, y, width, height; } GlassRect;
typedef struct { void *window; int dock, height, count, touching, pointer_left; double first, last, touch_x, touch_y, mouse_x, mouse_y; char *tip; double tip_x, tip_y; void *held; long long touch_started; int hold_ready, touch_moved, reordered, original_index; double start_x, start_y; long long next_motion_check; int motion_enabled; } GlassBar;
typedef struct {
    double zoom;
    int size, top, bottom, panel_hover, drawing_hover;
    const char *art_file;
    void *strip;
    int frames, frame, inside;
    long long started, last_touch, last_inside;
} GlassItem;
extern void gtk_style_context_add_class(void *, const char *);
extern void gtk_style_context_remove_class(void *, const char *);
extern void *gtk_bin_get_child(void *);
extern void g_signal_emit_by_name(void *, const char *, ...);
extern void gtk_widget_set_halign(void *, int);
extern void gtk_widget_set_valign(void *, int);
extern void gtk_widget_set_size_request(void *, int, int);
extern void gtk_widget_set_margin_top(void *, int);
extern void gtk_widget_set_margin_bottom(void *, int);
extern void gtk_widget_get_allocation(void *, GlassRect *);
extern int gtk_widget_translate_coordinates(void *, void *, int, int, int *, int *);
extern int gtk_widget_get_allocated_width(void *);
extern void gtk_widget_queue_draw(void *);
extern void gtk_widget_set_app_paintable(void *, int);
extern void gtk_widget_add_events(void *, int);
extern void *gtk_widget_get_window(void *);
extern void *gtk_widget_get_display(void *);
extern void *gdk_display_get_default_seat(void *);
extern void *gdk_seat_get_pointer(void *);
extern void *gtk_event_controller_motion_new(void *);
extern void gtk_event_controller_set_propagation_phase(void *, int);
extern void *gdk_device_get_window_at_position(void *, int *, int *);
extern void *gdk_window_get_toplevel(void *);
extern void gtk_widget_set_has_tooltip(void *, int);
extern void *gtk_widget_create_pango_layout(void *, const char *);
extern void *pango_font_description_from_string(const char *);
extern void pango_font_description_free(void *);
extern void pango_layout_set_font_description(void *, const void *);
extern void pango_layout_set_width(void *, int);
extern void pango_layout_set_ellipsize(void *, int);
extern void pango_layout_get_pixel_size(void *, int *, int *);
extern void pango_cairo_show_layout(void *, void *);
extern void cairo_move_to(void *, double, double);
extern void cairo_line_to(void *, double, double);
extern void cairo_curve_to(void *, double, double, double, double, double, double);
extern void cairo_close_path(void *);
extern void cairo_fill_preserve(void *);
extern void *gdk_window_get_device_position(void *, void *, int *, int *, unsigned int *);
extern void g_object_set_data_full(void *, const char *, void *, void (*)(void *));
extern void *g_object_ref(void *);
extern GType gtk_image_get_type(void);
extern int gtk_image_get_storage_type(void *);
extern void *gtk_image_get_pixbuf(void *);
extern void gtk_image_set_from_pixbuf(void *, void *);
extern void gtk_image_set_pixel_size(void *, int);
extern void *gdk_pixbuf_scale_simple(void *, int, int, int);
extern void *gdk_pixbuf_new_from_file(const char *, void *);
extern int gdk_pixbuf_get_width(void *);
extern int gdk_pixbuf_get_height(void *);
extern void *gdk_pixbuf_new_subpixbuf(void *, int, int, int, int);
extern const char *g_get_user_config_dir(void);
extern char *g_path_get_dirname(const char *);
extern char *g_build_filename(const char *, ...);
extern void *g_desktop_app_info_new(const char *);
extern void *g_app_info_get_icon(void *);
extern void *gtk_icon_theme_get_for_screen(void *);
extern void *gtk_icon_theme_lookup_by_gicon(void *, void *, int, int);
extern void *gtk_icon_info_load_icon(void *, void *);
extern int gdk_event_get_event_type(void *);
extern int gdk_event_get_root_coords(void *, double *, double *);
extern int gdk_window_get_origin(void *, int *, int *);
extern void gtk_widget_input_shape_combine_region(void *, void *);
extern void *cairo_region_create(void);
extern void cairo_region_destroy(void *);
extern int cairo_region_union_rectangle(void *, const GlassRect *);
extern void cairo_save(void *);
extern void cairo_restore(void *);
extern void cairo_translate(void *, double, double);
extern void cairo_scale(void *, double, double);
extern void cairo_new_path(void *);
extern void cairo_arc(void *, double, double, double, double, double);
extern void cairo_set_line_width(void *, double);
extern void cairo_set_line_cap(void *, int);
extern void cairo_set_source_rgba(void *, double, double, double, double);
extern void cairo_set_source(void *, void *);
extern void cairo_set_operator(void *, int);
extern void cairo_paint(void *);
extern void cairo_stroke(void *);
extern void *cairo_pattern_create_linear(double, double, double, double);
extern void cairo_pattern_add_color_stop_rgba(void *, double, double, double, double, double);
extern void cairo_pattern_destroy(void *);
extern long long g_get_monotonic_time(void);

extern void *gtk_gesture_drag_new(void *);
extern void gtk_gesture_single_set_touch_only(void *, int);
extern int gtk_gesture_set_state(void *, int);
extern void *gtk_gesture_get_last_updated_sequence(void *);
extern void *gtk_gesture_get_last_event(void *, void *);
extern void gtk_box_reorder_child(void *, void *, int);
extern List *gtk_container_get_children(void *);
extern int g_app_info_launch(void *, void *, void *, void *);

#define GLASS_RADIUS 470.0
#define GLASS_OFFSET 24
#define GLASS_WIDTH 800

static double glass_y(GlassBar *bar, double x)
{
    double dx = x - gtk_widget_get_allocated_width(bar->window) / 2.0;
    double rise = sqrt(fmax(1, GLASS_RADIUS * GLASS_RADIUS - dx * dx));
    return bar->dock ? bar->height + GLASS_OFFSET - 540 + rise : 540 - GLASS_OFFSET - rise;
}

static void glass_arc(void *cr, GlassBar *bar, double radius)
{
    double cx = gtk_widget_get_allocated_width(bar->window) / 2.0;
    double cy = bar->dock ? bar->height + GLASS_OFFSET - 540 : 540 - GLASS_OFFSET;
    double a = asin(fmax(-0.95, fmin(0.95, (bar->first - cx) / GLASS_RADIUS)));
    double b = asin(fmax(-0.95, fmin(0.95, (bar->last - cx) / GLASS_RADIUS)));
    cairo_new_path(cr);
    if (bar->dock) cairo_arc(cr, cx, cy, radius, M_PI / 2 - b, M_PI / 2 - a);
    else cairo_arc(cr, cx, cy, radius, -M_PI / 2 + a, -M_PI / 2 + b);
}

/* Draw the reference-style dark pill and its small rounded pointer within
 * the existing transparent surface. It cannot steal focus or pointer input. */
static const char wifi_testing[] = "Testing speed…";

static void glass_tooltip(GlassBar *bar, void *cr)
{
    if (!bar->tip || !*bar->tip) return;
    void *layout = gtk_widget_create_pango_layout(bar->window, bar->tip);
    void *font = pango_font_description_from_string("Rubik 17");
    pango_layout_set_font_description(layout, font); pango_font_description_free(font);
    int tw, th; pango_layout_get_pixel_size(layout, &tw, &th);
    if (tw > 280) { pango_layout_set_width(layout, 280 * 1024); pango_layout_set_ellipsize(layout, 3); pango_layout_get_pixel_size(layout, &tw, &th); }
    int spinning = !strncmp(bar->tip, wifi_testing, strlen(wifi_testing));
    double w = tw + 34 + (spinning ? 24 : 0), h = fmax(44, th + 14), r = 22;
    double x = fmax(8, fmin(gtk_widget_get_allocated_width(bar->window) - w - 8, bar->tip_x - w / 2));
    double y = bar->dock ? bar->tip_y - h - 13 : bar->tip_y + 13;
    y = fmax(8, fmin(bar->height - h - 10, y));
    double cx = fmax(x + 30, fmin(x + w - 30, bar->tip_x));
    cairo_new_path(cr); cairo_move_to(cr, x+r, y);
    if (!bar->dock) {
        cairo_line_to(cr, cx-10, y);
        cairo_curve_to(cr, cx-5,y, cx-4,y-9, cx,y-9);
        cairo_curve_to(cr, cx+4,y-9, cx+5,y, cx+10,y);
    }
    cairo_line_to(cr,x+w-r,y); cairo_arc(cr,x+w-r,y+r,r,-M_PI/2,0);
    cairo_line_to(cr,x+w,y+h-r); cairo_arc(cr,x+w-r,y+h-r,r,0,M_PI/2);
    if (bar->dock) {
        cairo_line_to(cr,cx+10,y+h);
        cairo_curve_to(cr,cx+5,y+h,cx+4,y+h+9,cx,y+h+9);
        cairo_curve_to(cr,cx-4,y+h+9,cx-5,y+h,cx-10,y+h);
    }
    cairo_line_to(cr,x+r,y+h); cairo_arc(cr,x+r,y+h-r,r,M_PI/2,M_PI);
    cairo_line_to(cr,x,y+r); cairo_arc(cr,x+r,y+r,r,M_PI,3*M_PI/2); cairo_close_path(cr);
    cairo_set_source_rgba(cr,0.055,0.063,0.078,0.97); cairo_fill_preserve(cr);
    cairo_set_source_rgba(cr,0.65,0.69,0.76,0.30); cairo_set_line_width(cr,1); cairo_stroke(cr);
    cairo_set_source_rgba(cr,0.96,0.97,0.99,1); if (spinning) {
        double angle = fmod(g_get_monotonic_time() / 150000.0, 2 * M_PI);
        cairo_new_path(cr);
        cairo_arc(cr, x + 22, y + 21, 7, angle, angle + 1.5 * M_PI);
        cairo_set_line_width(cr, 2.5);
        cairo_stroke(cr);
    }
    cairo_move_to(cr,x+(w-tw)/2+(spinning ? 12 : 0),y+(h-th)/2);
    pango_cairo_show_layout(cr,layout); g_object_unref(layout);
}

static int glass_draw(void *widget, void *cr, void *data)
{
    (void)widget;
    GlassBar *bar = data;
    cairo_save(cr);
    cairo_set_operator(cr, 1); /* SOURCE: don't accumulate translucent coats. */
    cairo_set_source_rgba(cr, 0, 0, 0, 0); cairo_paint(cr);
    cairo_set_operator(cr, 2); /* OVER */
    if (!bar->count) { cairo_restore(cr); return 0; }
    double width = bar->dock ? 82 : 58;
    double middle = glass_y(bar, gtk_widget_get_allocated_width(bar->window) / 2.0);
    cairo_set_line_cap(cr, 1);
    /* Soft outside shade, a translucent body and two fine reflective rims. */
    for (int i = 4; i > 0; --i) {
        glass_arc(cr, bar, GLASS_RADIUS);
        cairo_set_line_width(cr, width + i * 3);
        cairo_set_source_rgba(cr, 0.01, 0.025, 0.045, 0.035); cairo_stroke(cr);
    }
    glass_arc(cr, bar, GLASS_RADIUS); cairo_set_line_width(cr, width + 2);
    cairo_set_source_rgba(cr, 0.25, 0.27, 0.28, 0.65); cairo_stroke(cr);
    void *gradient = cairo_pattern_create_linear(0, middle - 65, 0, middle + 65);
    cairo_pattern_add_color_stop_rgba(gradient, 0, 0.13, 0.15, 0.16, 0.96);
    cairo_pattern_add_color_stop_rgba(gradient, 0.42, 0.106, 0.125, 0.133, 0.97);
    cairo_pattern_add_color_stop_rgba(gradient, 1, 0.071, 0.086, 0.094, 0.98);
    glass_arc(cr, bar, GLASS_RADIUS); cairo_set_line_width(cr, width);
    cairo_set_source(cr, gradient); cairo_stroke(cr); cairo_pattern_destroy(gradient);
    glass_arc(cr, bar, GLASS_RADIUS + width / 2 - 1);
    cairo_set_line_width(cr, 1); cairo_set_source_rgba(cr, 0.42, 0.44, 0.45, 0.25); cairo_stroke(cr);
    glass_arc(cr, bar, GLASS_RADIUS - width / 2 + 1);
    cairo_set_line_width(cr, 1); cairo_set_source_rgba(cr, 0.25, 0.27, 0.28, 0.20); cairo_stroke(cr);
    glass_tooltip(bar, cr);
    cairo_restore(cr);
    return 0;
}

typedef struct { const char *id; GlassItem *item; int size; } GlassIconRequest;

static const char *glass_art_file(const char *id)
{
    static const struct { const char *id, *file; } icons[] = {
        {"aroundos-launchpad.desktop", "launchpad.png"},
        {"aroundos-files.desktop", "files.png"},
        {"aroundos-editor.desktop", "editor.png"},
        {"aroundos-terminal.desktop", "terminal.png"},
        {"x-terminal-emulator.desktop", "terminal.png"},
        {"aroundos-browser.desktop", "browser.png"},
        {"x-www-browser.desktop", "browser.png"},
        {"aroundos-settings.desktop", "settings.png"},
        {"aroundos-sleep.desktop", "sleep.png"},
    };
    for (size_t i = 0; i < sizeof(icons) / sizeof(icons[0]); i++)
        if (!strcmp(id, icons[i].id)) return icons[i].file;
    return NULL;
}

static void *glass_load_dock_art(const char *file, const char *folder)
{
    if (!file) return NULL;
    char *source = g_path_get_dirname(__FILE__);
    char *path = g_build_filename(source, "dock-icons", folder, file, (char *)NULL);
    void *art = gdk_pixbuf_new_from_file(path, NULL);
    g_free(path); g_free(source);
    /* Staged builds can outlive their temporary source directory. */
    if (!art && getenv("HOME")) {
        path = g_build_filename(getenv("HOME"), "AroundOS", "src",
            "round-desktop", "dock-icons", folder, file, (char *)NULL);
        art = gdk_pixbuf_new_from_file(path, NULL);
        g_free(path);
    }
    return art;
}

static void glass_free_item(void *data)
{
    GlassItem *item = data;
    if (item->strip) g_object_unref(item->strip);
    free(item);
}

static int glass_motion_enabled(void)
{
    const char *reduced = getenv("AROUNDOS_REDUCE_MOTION");
    if (reduced && (!strcmp(reduced, "1") || !strcasecmp(reduced, "true") ||
                    !strcasecmp(reduced, "yes"))) return 0;
    char *flag = g_build_filename(g_get_user_config_dir(), "aroundos-round", "dock-motion-off", (char *)NULL);
    int enabled = access(flag, F_OK) != 0;
    g_free(flag);
    return enabled;
}

/* A strip contains one row of square, 30 fps frames. Zero means use the
 * original cutout. A missing or malformed strip keeps the static behavior. */
static int glass_motion_frame(GlassItem *item, int inside, long long touch, long long now)
{
    if (!item->started && inside && (!item->inside || touch > item->last_touch)) {
        if (!item->frames) {
            item->frames = -1;
            item->strip = glass_load_dock_art(item->art_file, "motion");
            if (item->strip) {
                int w = gdk_pixbuf_get_width(item->strip), h = gdk_pixbuf_get_height(item->strip);
                if (h > 0 && w % h == 0 && w / h >= 3) item->frames = w / h;
            }
        }
        if (item->frames > 0) item->started = now;
    }
    /* GTK can briefly report leave/enter while magnification reallocates the
     * button under a stationary pointer. Re-arm after a sustained departure. */
    if (inside) {
        item->inside = 1;
        item->last_inside = now;
    } else if (now - item->last_inside >= 200000) {
        item->inside = 0;
    }
    if (touch) item->last_touch = touch;
    if (!item->started) return 0;
    int frame = (int)((now - item->started) * 30 / 1000000);
    if (frame < item->frames - 1) return frame;
    item->started = 0;
    return 0;
}

static void *glass_theme_icon(void *widget, const GlassIconRequest *request)
{
    void *app = strstr(request->id, ".desktop") ? g_desktop_app_info_new(request->id) : NULL;
    if (!app) return NULL;
    void *icon = g_app_info_get_icon(app);
    void *theme = gtk_icon_theme_get_for_screen(gtk_widget_get_screen(widget));
    void *info = icon ? gtk_icon_theme_lookup_by_gicon(theme, icon, request->size, 16) : NULL;
    void *scaled = info ? gtk_icon_info_load_icon(info, NULL) : NULL;
    if (info) g_object_unref(info);
    g_object_unref(app);
    return scaled;
}

static void glass_scale_image(void *widget, void *data)
{
    if (!g_type_check_instance_is_a(widget, gtk_image_get_type())) {
        if (g_type_check_instance_is_a(widget, gtk_container_get_type()))
            gtk_container_foreach(widget, glass_scale_image, data);
        return;
    }
    GlassIconRequest *request = data;
    if (!g_object_get_data(widget, "aroundos-glass-art-checked")) {
        void *art = glass_load_dock_art(request->item->art_file, "cutouts");
        if (art) g_object_set_data_full(widget, "aroundos-glass-art", art, g_object_unref);
        g_object_set_data(widget, "aroundos-glass-art-checked", (void *)1);
    }
    void *original = g_object_get_data(widget, "aroundos-glass-art");
    if (original && request->item->frame) {
        GlassItem *item = request->item;
        int side = gdk_pixbuf_get_height(item->strip);
        void *tile = gdk_pixbuf_new_subpixbuf(item->strip, side * item->frame, 0, side, side);
        void *scaled = gdk_pixbuf_scale_simple(tile, request->size, request->size, 2);
        g_object_unref(tile);
        if (scaled) {
            gtk_image_set_from_pixbuf(widget, scaled);
            g_object_unref(scaled);
            return;
        }
    }
    int custom = original != NULL;
    if (!custom) {
        if (gtk_image_get_storage_type(widget) != 1) {
            gtk_image_set_pixel_size(widget, request->size);
            return;
        }
        original = g_object_get_data(widget, "aroundos-glass-original");
        if (!original) {
            original = gtk_image_get_pixbuf(widget);
            if (!original) return;
            g_object_set_data_full(widget, "aroundos-glass-original", g_object_ref(original), g_object_unref);
        }
    }
    char key[64];
    snprintf(key, sizeof(key), "aroundos-glass-icon-%d", request->size);
    void *scaled = g_object_get_data(widget, key);
    if (!scaled) {
        if (!custom) scaled = glass_theme_icon(widget, request);
        if (!scaled) scaled = gdk_pixbuf_scale_simple(original, request->size, request->size, 2);
        if (!scaled) return;
        g_object_set_data_full(widget, key, scaled, g_object_unref);
    }
    gtk_image_set_from_pixbuf(widget, scaled);
}

typedef struct {
    GlassBar *bar;
    int pointer_x, pointer_y, changed;
    double tip_distance;
    void *region;
    long long now;
} GlassLayout;

/* Capture motion before child launchers/gestures consume the event. GTK
 * supplies coordinates in this bar's space; no Wayland global-position query. */
static void glass_pointer_motion(void *controller, double x, double y, void *data)
{
    (void)controller;
    GlassBar *bar = data;
    bar->mouse_x = x; bar->mouse_y = y; bar->pointer_left = 0;
}

static void glass_pointer_leave(void *controller, void *data)
{
    (void)controller;
    GlassBar *bar = data;
    bar->pointer_left = 1;
}

/* Own touch sequences in capture phase, before the native launcher drag and
 * long-press menu handlers. Mouse hover and mouse dragging remain native. */
static void glass_pick(void *widget, void *data)
{
    GlassBar *bar = data;
    if (!gtk_widget_get_visible(widget)) return;
    if (g_type_check_instance_is_a(widget, gtk_button_get_type())) {
        void *parent = gtk_widget_get_parent(widget);
        if (!parent || strcmp(gtk_widget_get_name(parent), "launchers")) return;
        int x, y; GlassRect a;
        gtk_widget_get_allocation(widget, &a);
        if (gtk_widget_translate_coordinates(widget, bar->window, 0, 0, &x, &y) &&
            bar->start_x >= x && bar->start_x < x+a.width &&
            bar->start_y >= y && bar->start_y < y+a.height)
            bar->held = widget;
    } else if (g_type_check_instance_is_a(widget, gtk_container_get_type()))
        gtk_container_foreach(widget, glass_pick, bar);
}

static void glass_touch_reset(GlassBar *bar, int rollback)
{
    if (bar->held) {
        void *parent = gtk_widget_get_parent(bar->held);
        if (rollback && bar->reordered && parent)
            gtk_box_reorder_child(parent, bar->held, bar->original_index);
        gtk_style_context_remove_class(gtk_widget_get_style_context(bar->held), "dock-pressed");
        g_object_unref(bar->held); bar->held = NULL;
    }
    bar->touching = bar->hold_ready = bar->touch_moved = bar->reordered = 0;
    bar->pointer_left = 1;
}

static void glass_drag_begin(void *gesture, double x, double y, void *data)
{
    GlassBar *bar = data;
    glass_touch_reset(bar, 1);
    bar->start_x = bar->touch_x = x; bar->start_y = bar->touch_y = y;
    gtk_container_foreach(bar->window, glass_pick, bar);
    if (!bar->held) { gtk_gesture_set_state(gesture, 2); return; }
    g_object_ref(bar->held);
    gtk_style_context_add_class(gtk_widget_get_style_context(bar->held), "dock-pressed");
    List *children = gtk_container_get_children(gtk_widget_get_parent(bar->held));
    int index = 0;
    for (List *p = children; p; p=p->next, index++)
        if (p->data == bar->held) bar->original_index = index;
    g_list_free(children);
    bar->touching = 1; bar->pointer_left = 1;
    bar->touch_started = g_get_monotonic_time();
    gtk_gesture_set_state(gesture, 1); /* CLAIMED: no native premature drag/tap. */
}

static void glass_drag_update(void *gesture, double dx, double dy, void *data)
{
    (void)gesture;
    GlassBar *bar = data;
    if (!bar->held) return;
    bar->touch_x = bar->start_x + dx; bar->touch_y = bar->start_y + dy;
    if (!bar->hold_ready) {
        if (!bar->touch_moved && hypot(dx, dy) > 12) {
            bar->touch_moved = 1;
            gtk_style_context_remove_class(gtk_widget_get_style_context(bar->held), "dock-pressed");
        }
        return; /* A swipe cannot become a hold later in the same contact. */
    }
    void *parent = gtk_widget_get_parent(bar->held);
    if (!parent || fabs(dy) > 100) return;
    List *children = gtk_container_get_children(parent);
    int index = 0, destination = -1;
    double finger = bar->start_x + dx;
    int hx=0, hy=0;
    gtk_widget_translate_coordinates(bar->held, bar->window, 0, 0, &hx, &hy);
    double held_center = hx + gtk_widget_get_allocated_width(bar->held)/2.0;
    for (List *p=children; p; p=p->next, index++) {
        if (p->data == bar->held) continue;
        int x=0, y=0;
        gtk_widget_translate_coordinates(p->data, bar->window, 0, 0, &x, &y);
        double center = x + gtk_widget_get_allocated_width(p->data)/2.0;
        if ((center > held_center && finger > center+8) ||
            (center < held_center && finger < center-8)) {
            destination = index;
            if (center < held_center) break;
        }
    }
    g_list_free(children);
    if (destination >= 0) {
        gtk_box_reorder_child(parent, bar->held, destination);
        bar->reordered = 1;
    }
}

static void glass_drag_cancel(void *gesture, void *sequence, void *data)
{
    (void)gesture; (void)sequence;
    glass_touch_reset(data, 1);
}

static void glass_drag_end(void *gesture, double dx, double dy, void *data)
{
    GlassBar *bar = data;
    if (!bar->held) return;
    void *event = gtk_gesture_get_last_event(gesture, gtk_gesture_get_last_updated_sequence(gesture));
    if (!event || gdk_event_get_event_type(event) != 39) {
        glass_touch_reset(bar, 1); return;
    }
    if (bar->reordered) {
        /* Use the panel's own config writer; it preserves all other settings. */
        void (*save)(const char *) = dlsym(RTLD_DEFAULT, "replace_launchers");
        char order[8192] = "";
        List *children = gtk_container_get_children(gtk_widget_get_parent(bar->held));
        for (List *p=children; p; p=p->next) {
            const char *name = gtk_widget_get_name(p->data);
            size_t n = strlen(name);
            if (n > 8 && !strcmp(name+n-8, ".desktop") && strlen(order)+n+1 < sizeof(order)) {
                strncat(order, name, n-8); strcat(order, " ");
            }
        }
        g_list_free(children);
        if (save) save(order);
    } else if (!bar->hold_ready && !bar->touch_moved && hypot(dx,dy) <= 12) {
        void *app = g_desktop_app_info_new(gtk_widget_get_name(bar->held));
        if (app) { g_app_info_launch(app, NULL, NULL, NULL); g_object_unref(app); }
    }
    glass_touch_reset(bar, 0);
}

/* Keep NetworkManager queries off the GTK thread. Only refresh while hovered. */
extern void *g_thread_new(const char *, void *(*)(void *), void *);
extern void g_thread_unref(void *);
extern guint g_idle_add(int (*)(void *), void *);
extern char *g_utf8_make_valid(const char *, long);
static char *wifi_summary;
static int wifi_pending;
static long long wifi_updated;

static int glass_wifi_ready(void *summary)
{
    g_free(wifi_summary);
    wifi_summary = summary;
    wifi_updated = g_get_monotonic_time();
    wifi_pending = 0;
    return 0;
}

/* Bind to the verified IPv4 address so USB/Ethernet cannot supply the result. */
static double glass_wifi_transfer(const char *ip, int upload)
{
    char command[512];
    const char *prefix = upload ? "head -c 250000 /dev/zero | " : "";
    const char *transfer = upload
        ? "--data-binary @- -w '%{speed_upload}' https://speed.cloudflare.com/__up"
        : "-w '%{speed_download}' 'https://speed.cloudflare.com/__down?bytes=1000000'";
    snprintf(command, sizeof(command), "%sLC_ALL=C curl -q -fsS --interface %s --connect-timeout 4 --max-time 15 -o /dev/null %s 2>/dev/null",
             prefix, ip, transfer);
    FILE *stream = popen(command, "r");
    if (!stream) return 0;
    char output[64] = "";
    fgets(output, sizeof(output), stream);
    int status = pclose(stream);
    /* A timed-out download can still measure bytes actually received. */
    if (status != 0 && (upload || status != (28 << 8))) return 0;
    return atof(output) * 8.0 / 1000000.0;
}

static int glass_wifi_loading(void *summary)
{
    g_free(wifi_summary);
    wifi_summary = summary;
    return 0;
}

static void *glass_wifi_query(void *unused)
{
    (void)unused;
    char line[1024], summary[1200] = "Wi-Fi disconnected";
    FILE *list = popen("LC_ALL=C.UTF-8 nmcli -w 2 -t -e no -f IN-USE,DEVICE,SSID device wifi list --rescan no 2>/dev/null", "r");
    int found = 0;
    while (list && fgets(line, sizeof(line), list)) {
        if (found || strncmp(line, "*:", 2)) continue;
        char *device = line + 2, *ssid = strchr(device, ':');
        if (!ssid) continue;
        *ssid++ = 0;
        ssid[strcspn(ssid, "\r\n")] = 0;
        char ip[INET_ADDRSTRLEN] = "";
        struct ifaddrs *addresses;
        if (getifaddrs(&addresses) == 0) {
            for (struct ifaddrs *it = addresses; it; it = it->ifa_next) {
                if (!it->ifa_addr || it->ifa_addr->sa_family != AF_INET || strcmp(device, it->ifa_name)) continue;
                inet_ntop(AF_INET, &((struct sockaddr_in *)it->ifa_addr)->sin_addr, ip, sizeof(ip));
                break;
            }
            freeifaddrs(addresses);
        }
        char speed[96];
        snprintf(summary, sizeof(summary), "%s\n%s\n%s", wifi_testing, *ssid ? ssid : "Hidden network", *ip ? ip : "Waiting for IP");
        g_idle_add(glass_wifi_loading, g_utf8_make_valid(summary, -1));
        double down = *ip ? glass_wifi_transfer(ip, 0) : 0;
        double up = down > 0 ? glass_wifi_transfer(ip, 1) : 0;
        if (down > 0 && up > 0) snprintf(speed, sizeof(speed), "↓ %.2f  ↑ %.2f Mbps", down, up);
        else strcpy(speed, "Speed test unavailable");
        snprintf(summary, sizeof(summary), "%s\n%s\n%s", speed, *ssid ? ssid : "Hidden network", *ip ? ip : "Waiting for IP");
        found = 1;
    }
    if (!list || pclose(list) != 0) strcpy(summary, "Wi-Fi status unavailable");
    g_idle_add(glass_wifi_ready, g_utf8_make_valid(summary, -1));
    return NULL;
}

static const char *glass_wifi_title(void)
{
    static long long last_hover;
    long long now = g_get_monotonic_time();
    if (!wifi_pending && (!wifi_summary || (now - last_hover > 500000 && now - wifi_updated > 5000000))) {
        wifi_pending = 1;
        g_free(wifi_summary);
        wifi_summary = NULL;
        g_thread_unref(g_thread_new("wifi-tooltip", glass_wifi_query, NULL));
    }
    last_hover = now;
    return wifi_summary ? wifi_summary : wifi_testing;
}

static void glass_disable_native_tip(void *widget, void *unused)
{
    gtk_widget_set_has_tooltip(widget, 0);
    if (g_type_check_instance_is_a(widget, gtk_container_get_type()))
        gtk_container_foreach(widget, glass_disable_native_tip, unused);
}

/* Only the artwork moves. The native button and the arc keep their positions
 * while both mapped cutouts and ordinary GTK icons use their usual draw path. */
static int glass_draw_panel_hover(void *button, void *cr, void *data)
{
    GlassItem *item = data;
    if (item->zoom == 0 || item->drawing_hover) return 0;
    double cx = gtk_widget_get_allocated_width(button) / 2.0;
    double cy = gtk_widget_get_allocated_height(button) / 2.0;
    double scale = 1.0 + (6.0 / 32.0) * item->zoom;
    cairo_save(cr);
    cairo_translate(cr, cx, cy + 4.0 * item->zoom);
    cairo_scale(cr, scale, scale);
    cairo_translate(cr, -cx, -cy);
    /* Continue the draw signal at the current allocation. gtk_widget_draw()
     * rejects a pending resize (for example from first-hover style changes),
     * leaving this handled frame blank. We are already in GTK's draw pass:
     * emit directly, with the guard allowing native drawing exactly once. */
    int handled = 0;
    item->drawing_hover = 1;
    g_signal_emit_by_name(button, "draw", cr, &handled);
    item->drawing_hover = 0;
    cairo_restore(cr);
    return 1;
}

static void glass_layout_item(void *widget, void *data)
{
    GlassLayout *layout = data;
    GlassBar *bar = layout->bar;
    if (!gtk_widget_get_visible(widget)) return;
    const char *name = gtk_widget_get_name(widget);
    int control = g_type_check_instance_is_a(widget, gtk_button_get_type())
        || !strcmp(name, "netman") || !strcmp(name, "clock") || !strcmp(name, "volumepulse");
    if (!control) {
        if (g_type_check_instance_is_a(widget, gtk_container_get_type()))
            gtk_container_foreach(widget, glass_layout_item, data);
        return;
    }
    GlassRect allocation;
    gtk_widget_get_allocation(widget, &allocation);
    int x = 0, y = 0;
    gtk_widget_translate_coordinates(widget, bar->window, 0, 0, &x, &y);
    double center = x + allocation.width / 2.0;
    if (allocation.width < 2) return;
    GlassItem *item = g_object_get_data(widget, "aroundos-glass-item");
    if (!item) {
        item = calloc(1, sizeof(*item)); item->top = item->bottom = -1;
        item->art_file = bar->dock ? glass_art_file(name) : NULL;
        item->panel_hover = !bar->dock && (g_object_get_data(widget, "aroundos-task-watch") != NULL ||
            !strcmp(name, "clock") || !strcmp(name, "netman"));
        g_object_set_data_full(widget, "aroundos-glass-item", item, glass_free_item);
        if (item->panel_hover)
            g_signal_connect_data(widget, "draw", (void (*)(void))glass_draw_panel_hover, item, NULL, 0);
        gtk_widget_set_valign(widget, 0);
        gtk_widget_add_events(widget, (1 << 2) | (1 << 12) | (1 << 13));

    }
    int wifi = !bar->dock && !strcmp(name, "netman");
    if (wifi) glass_disable_native_tip(widget, NULL);
    else gtk_widget_set_has_tooltip(widget, 0);
    double target = 0;
    if (bar->dock && layout->pointer_y > 20 && layout->pointer_y < bar->height) {
        double distance = (center - layout->pointer_x) / 92.0;
        target = exp(-distance * distance * 1.6);
        if (target < 0.015) target = 0;
    } else if (item->panel_hover && bar->motion_enabled) {
        target = layout->pointer_x >= x && layout->pointer_x < x + allocation.width &&
                 layout->pointer_y >= y && layout->pointer_y < y + allocation.height;
    }
    double previous_zoom = item->zoom;
    item->zoom += (target - item->zoom) * 0.26;
    if (fabs(target - item->zoom) < 0.005) item->zoom = target;
    if (item->panel_hover) {
        if (!bar->motion_enabled) item->zoom = 0;
        if (item->zoom != previous_zoom) gtk_widget_queue_draw(widget);
    }
    int icon = bar->dock ? (int)lround(56 + 34 * item->zoom) : 32;
    int size = bar->dock ? icon + 18 : 48;
    int top = (int)lround(glass_y(bar, center) - size / 2.0 - (bar->dock ? 22 * item->zoom + (bar->hold_ready && bar->held == widget ? 10 : 0) : 0));
    int bottom = bar->height - top - size;
    if (top < 0) top = 0;
    if (bottom < 0) bottom = 0;
    int frame = 0;
    if (item->art_file && bar->motion_enabled && !bar->hold_ready) {
        int inside = layout->pointer_x >= x && layout->pointer_x < x + allocation.width &&
            layout->pointer_y >= top - 8 && layout->pointer_y <= top + size + 8;
        long long press = bar->touching && bar->held == widget ? bar->touch_started : 0;
        frame = glass_motion_frame(item, inside, press, layout->now);
    } else {
        item->inside = 0;
        item->started = 0;
    }
    if (bar->dock && (item->size != size || item->frame != frame)) {
        item->frame = frame;
        GlassIconRequest request = {name, item, icon};
        glass_scale_image(widget, &request);
    }
    if (item->size != size) {
        item->size = size; gtk_widget_set_size_request(widget, size, size);
        layout->changed = 1;
    }
    if (item->top != top) { item->top = top; gtk_widget_set_margin_top(widget, top); layout->changed = 1; }
    if (item->bottom != bottom) { item->bottom = bottom; gtk_widget_set_margin_bottom(widget, bottom); layout->changed = 1; }
    if (center < bar->first) bar->first = center;
    /* The clock label can be wider than an icon. Keep 12 px inside the
     * 29 px rounded cap even when the time uses the full widget width. */
    double end = bar->dock ? center : fmax(center, x + allocation.width + 12 - 29);
    if (end > bar->last) bar->last = end;
    bar->count++;
    double distance = fabs(center - layout->pointer_x);
    if (distance < layout->tip_distance && layout->pointer_y >= top - 12 && layout->pointer_y <= top + size + 14) {
        char *title = wifi ? NULL : gtk_widget_get_tooltip_text(widget);
        const char *display = wifi ? glass_wifi_title() : title;
        if (display && *display) {
            free(bar->tip); bar->tip = strdup(display);
            bar->tip_x = center; bar->tip_y = bar->dock ? top : top + size;
            layout->tip_distance = distance;
        }
        g_free(title);
    }
    GlassRect hit = {x - 4, top - 4, allocation.width + 8, size + 8};
    cairo_region_union_rectangle(layout->region, &hit);
}

static int glass_tick(void *data)
{
    GlassBar *bar = data;
    if (!bar->window) { free(bar->tip); free(bar); return 0; }
    if (!gtk_widget_get_visible(bar->window)) { glass_touch_reset(bar, 1); return 1; }
    void *surface = gtk_widget_get_window(bar->window);
    if (!surface) return 1;
    long long now = g_get_monotonic_time();
    if (now >= bar->next_motion_check) {
        bar->motion_enabled = glass_motion_enabled();
        bar->next_motion_check = now + 1000000;
    }
    int px = -10000, py = -10000;
    if (!bar->pointer_left) { px = (int)bar->mouse_x; py = (int)bar->mouse_y; }
    if (bar->touching) {
        px = (int)bar->touch_x; py = (int)bar->touch_y;
        if (!bar->touch_moved && !bar->hold_ready && g_get_monotonic_time()-bar->touch_started >= 550000) {
            bar->hold_ready = 1;
            gtk_style_context_remove_class(gtk_widget_get_style_context(bar->held), "dock-pressed");
        }
        /* Keep rearranging stable, but let ordinary finger slides magnify. */
        if (bar->hold_ready) px = py = -10000;
    }
    double old_first = bar->first, old_last = bar->last;
    int old_count = bar->count;
    bar->first = 10000; bar->last = -10000; bar->count = 0;
    char *old_tip = bar->tip; double old_tip_x = bar->tip_x, old_tip_y = bar->tip_y;
    bar->tip = NULL;
    GlassLayout layout = {bar, px, py, 0, 55, cairo_region_create(), now};
    gtk_container_foreach(bar->window, glass_layout_item, &layout);
    if (bar->count) {
        /* The plate is an arc, not a large invisible rectangle over applications. */
        int radius = bar->dock ? 43 : 31;
        for (int x = (int)bar->first - radius; x <= (int)bar->last + radius; x += 4) {
            double nearest = fmax(bar->first, fmin(bar->last, x));
            double dx = x - nearest;
            int half = (int)sqrt(fmax(0, radius * radius - dx * dx));
            GlassRect strip = {x, (int)glass_y(bar, nearest) - half, 4, 2 * half};
            cairo_region_union_rectangle(layout.region, &strip);
        }
    }
    int changed = layout.changed || old_count != bar->count || old_first != bar->first || old_last != bar->last;
    if (changed) gtk_widget_input_shape_combine_region(bar->window, layout.region);
    cairo_region_destroy(layout.region);
    if ((old_tip == NULL) != (bar->tip == NULL) || (old_tip && bar->tip && strcmp(old_tip, bar->tip)) ||
        old_tip_x != bar->tip_x || old_tip_y != bar->tip_y) changed = 1;
    free(old_tip);
    if (changed || (bar->tip && !strncmp(bar->tip, wifi_testing, strlen(wifi_testing)))) gtk_widget_queue_draw(bar->window);
    return 1;
}

static void glass_reset_motion(void *widget, void *data)
{
    GlassItem *item = g_object_get_data(widget, "aroundos-glass-item");
    if (item) {
        item->started = item->inside = 0;
        if (item->frame) {
            item->frame = 0;
            GlassIconRequest request = {gtk_widget_get_name(widget), item, item->size - 18};
            glass_scale_image(widget, &request);
        }
    } else if (g_type_check_instance_is_a(widget, gtk_container_get_type())) {
        gtk_container_foreach(widget, glass_reset_motion, data);
    }
}

static void glass_dock_unmap(void *widget, void *data)
{
    glass_touch_reset(data, 1);
    gtk_container_foreach(widget, glass_reset_motion, NULL);
}

static void glass_destroyed(void *data, void *object)
{
    (void)object;
    glass_touch_reset(data, 1);
    ((GlassBar *)data)->window = NULL;
}

static void glass_attach(void *window)
{
    const char *name = gtk_widget_get_name(window);
    if (strcmp(name, "PanelToplevel") && strcmp(name, "DockToplevel")) return;
    if (g_object_get_data(window, "aroundos-glass-bar")) return;
    int (*is_layer)(void *) = dlsym(RTLD_DEFAULT, "gtk_layer_is_layer_window");
    void (*anchor)(void *, int, int) = dlsym(RTLD_DEFAULT, "gtk_layer_set_anchor");
    void (*margin)(void *, int, int) = dlsym(RTLD_DEFAULT, "gtk_layer_set_margin");
    if (!is_layer || !is_layer(window) || !anchor || !margin) return;
    GlassBar *bar = calloc(1, sizeof(*bar));
    bar->window = window; bar->dock = !strcmp(name, "DockToplevel"); bar->height = bar->dock ? 220 : 180;
    g_object_set_data(window, "aroundos-glass-bar", bar);
    gtk_widget_set_app_paintable(window, 1);
    anchor(window, 0, 0); anchor(window, 1, 0);
    margin(window, bar->dock ? 3 : 2, GLASS_OFFSET);
    gtk_widget_set_size_request(window, GLASS_WIDTH, bar->height);
    void *content = gtk_bin_get_child(window);
    if (content) {
        gtk_widget_set_halign(content, 3);
        gtk_widget_set_size_request(content, -1, bar->height);
    }
    g_signal_connect_data(window, "draw", (void (*)(void))glass_draw, bar, NULL, 0);
    bar->pointer_left = 1;
    gtk_widget_add_events(window, (1 << 2) | (1 << 12) | (1 << 13));
    void *motion = gtk_event_controller_motion_new(window);
    gtk_event_controller_set_propagation_phase(motion, 1); /* GTK_PHASE_CAPTURE */
    g_signal_connect_data(motion, "enter", (void (*)(void))glass_pointer_motion, bar, NULL, 0);
    g_signal_connect_data(motion, "motion", (void (*)(void))glass_pointer_motion, bar, NULL, 0);
    g_signal_connect_data(motion, "leave", (void (*)(void))glass_pointer_leave, bar, NULL, 0);
    g_object_set_data_full(window, "aroundos-glass-motion", motion, g_object_unref);
    if (bar->dock) {
        g_signal_connect_data(window, "unmap", (void (*)(void))glass_dock_unmap, bar, NULL, 0);
        void *drag = gtk_gesture_drag_new(window);
        gtk_gesture_single_set_touch_only(drag, 1);
        gtk_event_controller_set_propagation_phase(drag, 1);
        g_signal_connect_data(drag, "drag-begin", (void (*)(void))glass_drag_begin, bar, NULL, 0);
        g_signal_connect_data(drag, "drag-update", (void (*)(void))glass_drag_update, bar, NULL, 0);
        g_signal_connect_data(drag, "drag-end", (void (*)(void))glass_drag_end, bar, NULL, 0);
        g_signal_connect_data(drag, "cancel", (void (*)(void))glass_drag_cancel, bar, NULL, 0);
        g_object_set_data_full(window, "aroundos-glass-touch", drag, g_object_unref);
    }
    g_object_weak_ref(window, glass_destroyed, bar);
    g_timeout_add(33, glass_tick, bar);
}
