import conftest
import os
import pytest
from conftest import PROCESS_SHUTDOWN_TIME
from herbstluftwm.types import Point
from Xlib import X
import Xlib


def test_net_wm_desktop_after_load(hlwm, x11):
    hlwm.call('add anothertag')
    win, _ = x11.create_client()
    hlwm.call('true')
    assert x11.get_property('_NET_WM_DESKTOP', win)[0] == 0
    layout = hlwm.call('dump').stdout

    hlwm.call(['load', 'anothertag', layout])

    assert x11.get_property('_NET_WM_DESKTOP', win)[0] == 1


def test_net_wm_desktop_after_bring(hlwm, x11):
    hlwm.call('add anothertag')
    win, winid = x11.create_client()
    hlwm.call('true')
    assert x11.get_property('_NET_WM_DESKTOP', win)[0] == 0

    hlwm.call(['use', 'anothertag'])
    hlwm.call(['bring', winid])

    assert x11.get_property('_NET_WM_DESKTOP', win)[0] == 1


def test_net_wm_desktop_after_tag_index_increment(hlwm, x11):
    hlwm.call('add tag1')
    hlwm.call('add tag2')
    hlwm.call('add tag3')
    # put a new window on the tag with index 1
    hlwm.call('rule tag=tag1')
    win, winid = x11.create_client()
    assert x11.get_property('_NET_WM_DESKTOP', win)[0] == 1

    # move the tag3 to the beginning of the list
    hlwm.call('attr tags.by-name.tag3.index 0')
    # so the index of the tag of the client increased by one
    assert x11.get_property('_NET_WM_DESKTOP', win)[0] == 2


@pytest.mark.parametrize('method', ['index_change', 'tag_removal'])
def test_net_wm_desktop_after_tag_index_decrement(hlwm, method, x11):
    hlwm.call('add tag1')
    hlwm.call('add tag2')
    hlwm.call('add tag3')
    # put a new window on the tag with index 3
    hlwm.call('rule tag=tag3')
    win, winid = x11.create_client()
    assert hlwm.get_attr('tags.by-name.tag3.index') == '3'
    assert x11.get_property('_NET_WM_DESKTOP', win)[0] == 3

    if method == 'index_change':
        # move the tag1 to the end of the list
        hlwm.call('attr tags.by-name.tag1.index 3')
    elif method == 'tag_removal':
        # remove 'tag1' so all later tags experience a index shift
        hlwm.call('merge_tag tag1 default')

    # so the index of the tag of the client decreased by one
    assert hlwm.get_attr('tags.by-name.tag3.index') == '2'
    assert x11.get_property('_NET_WM_DESKTOP', win)[0] == 2


@pytest.mark.parametrize('new_idx', [0, 1, 2])
def test_net_wm_desktop_after_tag_index_direct_change(hlwm, x11, new_idx):
    hlwm.call('add tag1')
    hlwm.call('add tag2')
    hlwm.call('rule tag=tag2')
    win, winid = x11.create_client()
    assert hlwm.get_attr('tags.by-name.tag2.index') == '2'
    assert x11.get_property('_NET_WM_DESKTOP', win)[0] == 2

    hlwm.call(f'attr tags.by-name.tag2.index {new_idx}')

    assert int(hlwm.get_attr('tags.by-name.tag2.index')) == new_idx
    assert x11.get_property('_NET_WM_DESKTOP', win)[0] == new_idx


@pytest.mark.parametrize('focus_idx', range(0, 4))
@pytest.mark.parametrize('old_idx', range(0, 4))
@pytest.mark.parametrize('new_idx', range(0, 4))
def test_net_current_desktop_after_tag_index_change(hlwm, x11, focus_idx, old_idx, new_idx):
    hlwm.call('add tag1')
    hlwm.call('add tag2')
    hlwm.call('add tag3')

    hlwm.call(f'use_index {focus_idx}')
    x11.display.sync()
    assert int(hlwm.get_attr('tags.focus.index')) == x11.ewmh.getCurrentDesktop()
    focus_name = hlwm.get_attr('tags.focus.name')

    hlwm.call(f'attr tags.{old_idx}.index {new_idx}')

    x11.display.sync()
    assert int(hlwm.get_attr('tags.focus.index')) == x11.ewmh.getCurrentDesktop()
    assert focus_name == hlwm.get_attr('tags.focus.name')


@pytest.mark.parametrize('utf8names,desktop_names', [
    (False, ['default']),
    (False, ['foo']),
    (True, ['föö', 'bär']),
    (True, ['a', 'long', 'list', 'of', 'tag', 'names']),
    (True, ['an', 'empty', '', '', 'tagname']),
])
def test_read_desktop_names(hlwm_spawner, x11, utf8names, desktop_names):
    x11.set_property_textlist('_NET_DESKTOP_NAMES', desktop_names, utf8=utf8names)
    x11.display.sync()

    hlwm_proc = hlwm_spawner()
    hlwm = conftest.HlwmBridge(os.environ['DISPLAY'], hlwm_proc)

    desktop_names = [dn for dn in desktop_names if len(dn) > 0]

    assert hlwm.list_children('tags.by-name') == sorted(desktop_names)
    for idx, name in enumerate(desktop_names):
        assert hlwm.get_attr(f'tags.{idx}.name') == name

    hlwm_proc.shutdown()


def test_tags_restored_after_wmexec(hlwm, hlwm_process):
    tags = ['a', 'long', 'list', 'of', 'tag', 'names']
    expected_tags = ['default'] + tags

    for tag in tags:
        hlwm.call(['add', tag])

    # We need at least one client, otherwise xvfb messes with the test
    hlwm.create_client()

    # Restart hlwm:
    p = hlwm.unchecked_call(['wmexec', hlwm_process.bin_path, '--verbose'],
                            read_hlwm_output=False)
    assert p.returncode == 0
    hlwm_process.read_and_echo_output(until_stdout='hlwm started')

    assert hlwm.list_children('tags.by-name') == sorted(expected_tags)
    for idx, name in enumerate(expected_tags):
        assert hlwm.get_attr(f'tags.{idx}.name') == name


@pytest.mark.parametrize('desktops,client2desktop', [
    (2, [0, 1]),
    (2, [None, 1]),  # client without index set
    (2, [2, 1, 8, 0]),  # clients exceeding the index range
    (3, [1, 2]),  # no client on the focused tag
    (5, [1, 1, 0, 4, 4, 4]),
])
def test_client_initially_on_desktop(hlwm_spawner, x11, desktops, client2desktop):
    desktop_names = ['tag{}'.format(i) for i in range(0, desktops)]
    x11.set_property_textlist('_NET_DESKTOP_NAMES', desktop_names)
    clients = []
    for desktop_idx in client2desktop:
        winHandle, winid = x11.create_client(sync_hlwm=False)
        clients.append(winid)
        if desktop_idx is not None:
            x11.set_property_cardinal('_NET_WM_DESKTOP', [desktop_idx], window=winHandle)
    x11.display.sync()

    hlwm_proc = hlwm_spawner()
    hlwm = conftest.HlwmBridge(os.environ['DISPLAY'], hlwm_proc)

    for client_idx, desktop_idx in enumerate(client2desktop):
        winid = clients[client_idx]
        if desktop_idx is not None and desktop_idx in range(0, desktops):
            assert hlwm.get_attr(f'clients.{winid}.tag') \
                == desktop_names[desktop_idx]
        else:
            assert hlwm.get_attr(f'clients.{winid}.tag') \
                == desktop_names[0]

    # check that clients.focus matches the X11 input focus on all tags:
    for i in range(0, desktops):
        assert i == hlwm.attr.tags.focus.index()
        input_focus = x11.display.get_input_focus().focus
        if 'focus' in hlwm.list_children('clients'):
            # if a client is focused according to hlwm, it has the input focus:
            assert x11.winid_str(input_focus) == hlwm.attr.clients.focus.winid()
        else:
            # otherwise, the invisible hlwm dummy window is focused:
            assert input_focus.id == x11.get_property('_NET_SUPPORTING_WM_CHECK')[0]
        hlwm.call('use_index +1')

    hlwm_proc.shutdown()


def test_manage_transient_for_windows_on_startup(hlwm_spawner, x11):
    master_win, master_id = x11.create_client(sync_hlwm=False)
    dialog_win, dialog_id = x11.create_client(sync_hlwm=False)
    dialog_win.set_wm_transient_for(master_win)
    x11.display.sync()

    hlwm_proc = hlwm_spawner()
    hlwm = conftest.HlwmBridge(os.environ['DISPLAY'], hlwm_proc)

    assert hlwm.list_children('clients') \
        == sorted([master_id, dialog_id, 'focus'])
    hlwm_proc.shutdown()


@pytest.mark.parametrize('swap_monitors_to_get_tag', [True, False])
@pytest.mark.parametrize('on_another_monitor', [True, False])
@pytest.mark.parametrize('tag_idx', [0, 1])
def test_ewmh_set_current_desktop(hlwm, x11, swap_monitors_to_get_tag, on_another_monitor, tag_idx):
    hlwm.call(['set', 'swap_monitors_to_get_tag', hlwm.bool(swap_monitors_to_get_tag)])
    hlwm.call('add otherTag')
    hlwm.call('add anotherTag')

    if on_another_monitor:
        hlwm.call('add_monitor 800x600+800+0 otherTag')

    x11.ewmh.setCurrentDesktop(tag_idx)
    x11.display.sync()

    assert int(hlwm.get_attr('tags.focus.index')) == tag_idx
    if swap_monitors_to_get_tag or not on_another_monitor or tag_idx == 0:
        assert int(hlwm.get_attr('monitors.focus.index')) == 0
    else:
        assert int(hlwm.get_attr('monitors.focus.index')) == 1


def test_ewmh_set_current_desktop_invalid_idx(hlwm, hlwm_process, x11):
    with hlwm_process.wait_stderr_match('_NET_CURRENT_DESKTOP: invalid index'):
        x11.ewmh.setCurrentDesktop(4)
        x11.display.sync()
    assert int(hlwm.get_attr('tags.focus.index')) == 0


def test_wm_state_type(hlwm, x11):
    win, _ = x11.create_client(sync_hlwm=True)
    wm_state = x11.display.intern_atom('WM_STATE')
    prop = win.get_full_property(wm_state, X.AnyPropertyType)
    assert prop.property_type == wm_state
    assert len(prop.value) == 2


def test_wm_state_of_visible_client(hlwm, x11):
    win, _ = x11.create_client(sync_hlwm=True)
    wm_state = x11.display.intern_atom('WM_STATE')
    prop = win.get_full_property(wm_state, X.AnyPropertyType)
    assert prop.value[0] == 1  # NormalState


@pytest.mark.parametrize('show_for_a_moment', [True, False])
def test_wm_state_of_hidden_client(hlwm, x11, show_for_a_moment):
    hlwm.call('chain , add foo , rule tag=foo')
    win, _ = x11.create_client(sync_hlwm=True)
    wm_state = x11.display.intern_atom('WM_STATE')

    if show_for_a_moment:
        hlwm.call('use foo')
        hlwm.call('use_previous')

    prop = win.get_full_property(wm_state, X.AnyPropertyType)
    assert prop.value[0] == 3  # IconicState
    # see https://tronche.com/gui/x/icccm/sec-4.html#s-4.1.3.1


def test_ewmh_focus_client(hlwm, x11):
    hlwm.call('set focus_stealing_prevention off')
    # add another client that has the focus
    _, winid_focus = x11.create_client()
    winHandleToBeFocused, winid = x11.create_client()
    assert hlwm.get_attr('clients.focus.winid') == winid_focus

    x11.ewmh.setActiveWindow(winHandleToBeFocused)
    x11.display.flush()

    assert hlwm.get_attr('clients.focus.winid') == winid


@pytest.mark.parametrize('on_another_monitor', [True, False])
def test_ewmh_focus_client_on_other_tag(hlwm, x11, on_another_monitor):
    hlwm.call('set focus_stealing_prevention off')
    hlwm.call('add tag2')
    if on_another_monitor:  # if the tag shall be on another monitor
        hlwm.call('add_monitor 800x600+600+0')
    hlwm.call('rule tag=tag2 focus=off')
    # add another client that has the focus on the other tag
    x11.create_client()
    handle, winid = x11.create_client()
    assert 'focus' not in hlwm.list_children('clients')

    x11.ewmh.setActiveWindow(handle)
    x11.display.flush()

    assert hlwm.get_attr('tags.focus.name') == 'tag2'
    assert hlwm.get_attr('clients.focus.winid') == winid


def test_ewmh_move_client_to_tag(hlwm, x11):
    hlwm.call('set focus_stealing_prevention off')
    hlwm.call('add otherTag')
    winHandleToMove, winid = x11.create_client()
    assert hlwm.get_attr(f'clients.{winid}.tag') == 'default'

    x11.ewmh.setWmDesktop(winHandleToMove, 1)
    x11.display.sync()

    assert hlwm.get_attr(f'clients.{winid}.tag') == 'otherTag'


def test_ewmh_make_client_urgent(hlwm, hc_idle, x11):
    hlwm.call('set focus_stealing_prevention off')
    hlwm.call('add otherTag')
    hlwm.call('rule tag=otherTag')
    # create a new client that is not focused
    winHandle, winid = x11.create_client()
    assert hlwm.get_attr(f'clients.{winid}.urgent') == 'false'
    assert 'focus' not in hlwm.list_children('clients')
    # assert that this window really does not have wm hints set:
    assert winHandle.get_wm_hints() is None
    hc_idle.hooks()  # reset hooks

    demandsAttent = '_NET_WM_STATE_DEMANDS_ATTENTION'
    x11.ewmh.setWmState(winHandle, 1, demandsAttent)
    x11.display.flush()

    assert hlwm.get_attr(f'clients.{winid}.urgent') == 'true'
    assert ['tag_flags'] in hc_idle.hooks()


@pytest.mark.parametrize('focused', [True, False])
def test_ewmh_focused_client_never_urgent(hlwm, hc_idle, x11, focused):
    hlwm.call('set focus_stealing_prevention off')
    if not focused:
        # if the client shall not be focused, simply place it on
        # another tag
        hlwm.call('add otherTag')
        hlwm.call('rule tag=otherTag')
    winHandle, winid = x11.create_client()
    assert hlwm.get_attr(f'clients.{winid}.urgent') == 'false'
    hc_idle.hooks()  # reset hooks

    # mark the client urgent
    demandsAttent = '_NET_WM_STATE_DEMANDS_ATTENTION'
    x11.ewmh.setWmState(winHandle, 1, demandsAttent)
    x11.display.flush()

    assert hlwm.get_attr(f'clients.{winid}.urgent') == hlwm.bool(not focused)
    assert (['urgent', 'on', winid] in hc_idle.hooks()) == (not focused)


def test_ewmh_make_client_urgent_no_focus_stealing(hlwm, hc_idle, x11):
    hlwm.call('set focus_stealing_prevention on')
    hlwm.call('add otherTag')
    hlwm.call('rule tag=otherTag')

    # create a new client that is not focused
    winHandle, winid = x11.create_client()

    x11.ewmh.setActiveWindow(winHandle)
    x11.display.flush()

    assert hlwm.get_attr(f'clients.{winid}.urgent') == 'true'
    demandsAttent = '_NET_WM_STATE_DEMANDS_ATTENTION'
    assert demandsAttent in x11.ewmh.getWmState(winHandle, str=True)
    assert 'focus' not in hlwm.list_children('clients')
    assert 'default' == hlwm.get_attr('tags.focus.name')


@pytest.mark.parametrize('minimized', [True, False])
def test_minimization_announced(hlwm, x11, minimized):
    winHandle, winid = x11.create_client()

    hlwm.call(f'set_attr clients.{winid}.minimized {hlwm.bool(minimized)}')

    hidden = '_NET_WM_STATE_HIDDEN'
    assert (hidden in x11.ewmh.getWmState(winHandle, str=True)) == minimized


def xiconifywindow(display, window, screen):
    """Implementation of XIconifyWindow()"""
    wm_change_state = display.get_atom('WM_CHANGE_STATE')
    # IconicState of https://tronche.com/gui/x/icccm/sec-4.html#s-4.1.3.1
    iconic_state = 3
    event = Xlib.protocol.event.ClientMessage(
        window=window,
        client_type=wm_change_state,
        data=(32, [iconic_state, 0, 0, 0, 0]))
    mask = X.SubstructureRedirectMask | X.SubstructureNotifyMask
    screen.root.send_event(event, event_mask=mask)
    display.flush()


def test_minimize_via_xlib(hlwm, x11):
    winHandle, winid = x11.create_client()
    assert hlwm.get_attr(f'clients.{winid}.minimized') == 'false'

    xiconifywindow(x11.display, winHandle, x11.screen)

    assert hlwm.get_attr(f'clients.{winid}.minimized') == 'true'


def test_unminimize_via_xlib(hlwm, x11):
    winHandle, winid = x11.create_client()
    hlwm.call(f'set_attr clients.{winid}.minimized true')

    winHandle.map()
    x11.display.flush()

    assert hlwm.get_attr(f'clients.{winid}.minimized') == 'false'


def test_net_wmname(hlwm, x11):
    assert hlwm.attr.settings.wmname() == x11.ewmh.getWmName(x11.root).decode()

    newname = 'LG3D'
    hlwm.attr.settings.wmname = newname
    x11.sync_with_hlwm()
    assert x11.ewmh.getWmName(x11.root).decode() == newname


def test_net_supporting_wm_check(hlwm, x11):
    """
    Test _NET_SUPPORTING_WM_CHECK
    https://specifications.freedesktop.org/wm-spec/wm-spec-latest.html#idm45623487911552
    """
    winid_int = x11.get_property('_NET_SUPPORTING_WM_CHECK')[0]
    handle = x11.display.create_resource_object('window', winid_int)
    # "The child window MUST also have the _NET_SUPPORTING_WM_CHECK property set
    # to the ID of the child window."
    assert x11.get_property('_NET_SUPPORTING_WM_CHECK', window=handle)[0] == winid_int

    # "The child window MUST also have the _NET_WM_NAME property set to the
    # name of the Window Manager."
    assert x11.ewmh.getWmName(handle).decode() == x11.ewmh.getWmName(x11.root).decode()

    new_name = 'LG3D'
    hlwm.attr.settings.wmname = 'LG3D'
    x11.sync_with_hlwm()
    assert x11.ewmh.getWmName(x11.root).decode() == new_name
    assert x11.ewmh.getWmName(handle).decode() == new_name


def test_net_supported(hlwm, x11):
    """Test _NET_SUPPORTED"""
    # a list of all ewmh actions supported:
    supported_actions = x11.get_property('_NET_SUPPORTED')
    # test that the list contains the most important ones:
    expected_actions = [
        '_NET_CLIENT_LIST',
        '_NET_CURRENT_DESKTOP',
        '_NET_DESKTOP_NAMES',
        '_NET_NUMBER_OF_DESKTOPS',
        '_NET_SUPPORTED',
        '_NET_WM_DESKTOP',
        '_NET_WM_NAME',
        '_NET_WM_WINDOW_TYPE',
    ]
    for prop in expected_actions:
        atom = x11.display.intern_atom(prop)
        assert atom in supported_actions


def test_close_window(hlwm, x11):
    # we use hlwm's create_client and not x11's because
    # it's easier to wait for the process to shut down
    winid, proc = hlwm.create_client()
    assert winid in hlwm.list_children('clients')
    x11.ewmh.setCloseWindow(x11.window(winid))
    x11.sync_with_hlwm()

    # wait for client to shut down
    proc.wait(PROCESS_SHUTDOWN_TIME)
    assert winid not in hlwm.list_children('clients')


class NetWmMoveResize:
    # defines from the EWMH doc on _NET_WM_MOVERESIZE:
    # https://specifications.freedesktop.org/wm-spec/wm-spec-latest.html#idm45377754090464
    SIZE_TOPLEFT = 0
    SIZE_TOP = 1
    SIZE_TOPRIGHT = 2
    SIZE_RIGHT = 3
    SIZE_BOTTOMRIGHT = 4
    SIZE_BOTTOM = 5
    SIZE_BOTTOMLEFT = 6
    SIZE_LEFT = 7
    MOVE = 8   # movement only
    SIZE_KEYBOARD = 9   # size via keyboard
    MOVE_KEYBOARD = 10  # move via keyboard
    CANCEL = 11  # cancel operation


@pytest.mark.parametrize('action_nr,is_moving', [
    (NetWmMoveResize.MOVE, True),
    (NetWmMoveResize.MOVE_KEYBOARD, True),
    # test some resizing operations
    # (but not all, because hlwm does not distinguish anyway)
    (NetWmMoveResize.SIZE_KEYBOARD, False),
    (NetWmMoveResize.SIZE_RIGHT, False),
    (NetWmMoveResize.SIZE_BOTTOM, False),
    (NetWmMoveResize.SIZE_BOTTOMLEFT, False),
])
def test_initiate_drag(hlwm, mouse, x11, action_nr, is_moving):
    hlwm.attr.tags.focus.floating = True
    winHandle, winid = x11.create_client()
    geo_before = hlwm.attr.clients[winid].floating_geometry()
    mouse_pos = geo_before.center() + Point(2, 2)
    mouse.move_to(mouse_pos.x, mouse_pos.y)
    x11.ewmh._setProperty('_NET_WM_MOVERESIZE', [0, 0, action_nr, 1, 2], winHandle)
    x11.sync_with_hlwm()

    assert hlwm.attr.clients.dragged.winid() == winid

    delta = Point(30, 40)
    mouse.move_relative(delta.x, delta.y)

    geo_afterwards = hlwm.attr.clients[winid].floating_geometry()
    if is_moving:
        assert geo_before.size() == geo_afterwards.size()
        assert geo_before.topleft() + delta == geo_afterwards.topleft()
    else:
        # it's resizing
        assert geo_before.topleft() == geo_afterwards.topleft()
        assert geo_before.size() + delta == geo_afterwards.size()


def test_cancel_drag(hlwm, x11):
    hlwm.attr.tags.focus.floating = True
    winHandle, winid = x11.create_client()
    hlwm.call(['drag', winid, 'move'])

    def is_dragging():
        return 'dragged' in hlwm.list_children('clients')

    assert is_dragging()

    x11.ewmh._setProperty('_NET_WM_MOVERESIZE', [0, 0, NetWmMoveResize.CANCEL, 1, 2], winHandle)
    x11.sync_with_hlwm()

    assert not is_dragging()
