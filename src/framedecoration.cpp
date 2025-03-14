#include "framedecoration.h"

#include <X11/Xlib.h>
#include <X11/Xutil.h>
#include <vector>

#include "client.h"
#include "decoration.h"
#include "ewmh.h"
#include "layout.h"
#include "settings.h"
#include "stack.h"
#include "tag.h"
#include "utils.h"
#include "x11-utils.h"
#include "xconnection.h"

using std::shared_ptr;
using std::vector;

std::map<Window, FrameDecoration*> FrameDecoration::s_windowToFrameDecoration;

FrameDecoration::FrameDecoration(FrameLeaf& frame, HSTag* tag_, Settings* settings_)
    : frame_(frame)
    , visible(false)
    , window_transparent(false)
    , tag(tag_)
    , settings(settings_)
{
    XConnection& xcon = XConnection::get();
    // set window attributes
    XSetWindowAttributes at;
    at.background_pixel = BlackPixel(xcon.display(), xcon.screen());
    at.border_pixel = BlackPixel(xcon.display(), xcon.screen());
    at.override_redirect = True;
    at.bit_gravity       = StaticGravity;
    at.event_mask        = SubstructureRedirectMask|SubstructureNotifyMask
         |ExposureMask|VisibilityChangeMask
         |EnterWindowMask|LeaveWindowMask|FocusChangeMask
         |ButtonPress;
    int mask = CWOverrideRedirect | CWBorderPixel | CWEventMask;
    if (xcon.usesTransparency()) {
        mask = mask | CWColormap;
        at.colormap = xcon.colormap();
    }
    window = XCreateWindow(xcon.display(), xcon.root(),
                        42, 42, 42, 42, settings->frame_border_width(),
                        // DefaultDepth(xcon.display(), xcon.screen()),
                        xcon.depth(),
                        InputOutput,
                        xcon.visual(),
                        mask, &at);

    // set wm_class for window
    XClassHint *hint = XAllocClassHint();
    hint->res_name = (char*)HERBST_FRAME_CLASS;
    hint->res_class = (char*)HERBST_FRAME_CLASS;
    XSetClassHint(xcon.display(), window, hint);

    XFree(hint);

    // insert into static map
    s_windowToFrameDecoration[window] = this;

    // insert it to the stack
    slice = Slice::makeFrameSlice(window);
    tag->stack->insertSlice(slice);
}

FrameDecoration::~FrameDecoration() {
    // remove from map
    auto it = s_windowToFrameDecoration.find(window);
    HSWeakAssert(it != s_windowToFrameDecoration.end());
    s_windowToFrameDecoration.erase(it);

    XDestroyWindow(XConnection::get().display(), window);
    tag->stack->removeSlice(slice);
    delete slice;
}

void FrameDecoration::render(const FrameDecorationData& data, bool isFocused) {
    XConnection& xcon = XConnection::get();
    auto clientColor = [&](const Color& color) -> unsigned long {
        return xcon.allocColor(0, color);
    };
    unsigned long border_color;
    unsigned long bg_color;
    if (isFocused) {
        border_color = clientColor(settings->frame_border_active_color());
        bg_color = clientColor(settings->frame_bg_active_color);
    } else {
        border_color = clientColor(settings->frame_border_normal_color);
        bg_color = clientColor(settings->frame_bg_normal_color);
    }
    int bw = settings->frame_border_width();

    if (settings->smart_frame_surroundings() == SmartFrameSurroundings::hide_all
        && !data.hasParent) {
        bw = 0;
    }
    Rectangle rect = data.contentGeometry;
    XSetWindowBorderWidth(xcon.display(), window, bw);
    XMoveResizeWindow(xcon.display(), window,
                      rect.x - bw,
                      rect.y - bw,
                      rect.width, rect.height);

    if (settings->frame_border_inner_width() > 0
        && settings->frame_border_inner_width() < settings->frame_border_width()) {
        set_window_double_border(xcon.display(), window,
                settings->frame_border_inner_width(),
                clientColor(settings->frame_border_inner_color),
                border_color);
    } else {
        XSetWindowBorder(xcon.display(), window, border_color);
    }

    XSetWindowBackground(xcon.display(), window, bg_color);
    if (settings->frame_bg_transparent() || data.hasClients) {
        vector<Rectangle> holes;
        if (settings->frame_bg_transparent()) {
            int ftw = settings->frame_transparent_width();
            holes.push_back(Rectangle(ftw, ftw, rect.width - 2 * ftw, rect.height - 2 * ftw));
        }
        for (Client* client : frame_.clients) {
            Rectangle geom = client->dec->last_outer();
            geom.x -= data.contentGeometry.x;
            geom.y -= data.contentGeometry.y;
            holes.push_back(geom);
        }
        window_cut_rect_holes(xcon, window, rect.width, rect.height, holes);
        window_transparent = true;
    } else if (window_transparent) {
        window_make_intransparent(xcon, window, rect.width, rect.height);
        window_transparent = false;
    }
    if (isFocused) {
        Ewmh::get().setWindowOpacity(window, settings->frame_active_opacity()/100.0);
    } else {
        Ewmh::get().setWindowOpacity(window, settings->frame_normal_opacity()/100.0);
    }

    XClearWindow(xcon.display(), window);
}

void FrameDecoration::updateVisibility(const FrameDecorationData& data, bool isFocused)
{
    bool show = false;
    bool isRootFrame = frame_.parent_.expired();
    switch (settings->show_frame_decorations()) {
    case ShowFrameDecorations::none:
        show = false;
        break;
    case ShowFrameDecorations::nonempty:
        show = data.hasClients;
        break;
    case ShowFrameDecorations::focused:
        show = data.hasClients || isFocused;
        break;
    case ShowFrameDecorations::focused_if_multiple:
        show = data.hasClients || (isFocused && !isRootFrame);
        break;
    case ShowFrameDecorations::if_multiple:
        show = data.hasClients || !isRootFrame;
        break;
    case ShowFrameDecorations::all:
        show = true;
        break;
    }
    XConnection& xcon = XConnection::get();
    if (show != visible) {
        visible = show;
        if (visible) {
            XMapWindow(xcon.display(), window);
        } else {
            XUnmapWindow(xcon.display(), window);
        }
    }
}

void FrameDecoration::hide() {
    if (visible) {
        visible = false;
        XUnmapWindow(XConnection::get().display(), window);
    }
}

shared_ptr<FrameLeaf> FrameDecoration::frame()
{
    return frame_.thisLeaf();
}

/**
 * @brief Find a FrameDecoration to which a given X window belongs
 * @param the window id
 * @return
 */
FrameDecoration* FrameDecoration::withWindow(Window winid)
{
    auto it = s_windowToFrameDecoration.find(winid);
    if (it != s_windowToFrameDecoration.end()) {
        return it->second;
    } else {
        return nullptr;
    }
}

