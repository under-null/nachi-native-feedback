"""Local-file native joint display. No sockets or robot-command route."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import time


def presentation(data, now_ns):
    state = data.get('state', 'WAITING')
    received = data.get('sample_received_counter_ns')
    age = (now_ns - received) / 1e9 if type(received) is int else None
    if state == 'FAILED':
        return 'FAILED', False, age
    if state.startswith('COMPLETE') or state == 'STOPPED_BY_OPERATOR':
        return 'SAVED FINAL', False, age
    if state == 'RUNNING' and age is not None and 0 <= age < 0.5:
        return 'RECEIVING', True, age
    return ('STALE' if age is not None else 'WAITING'), False, age


def save_mark(path, name, data, now_ns):
    badge, recent, _ = presentation(data, now_ns)
    if not recent or not data.get('initial_samples_received') or len(data.get('values') or []) != 6:
        raise ValueError('A recent six-joint observation and ten initial samples are required')
    path.write_text(json.dumps({'pose': name, 'marked_counter_ns': now_ns,
                                'sample_received_counter_ns': data['sample_received_counter_ns'],
                                'values': data['values'], 'sample_count': data['samples'],
                                'measurement_age_known': False}, indent=2) + '\n', encoding='utf-8')


def main():
    import tkinter as tk  # Optional GUI; codec/tests need no Tk installation.
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data', type=Path, required=True)
    parser.add_argument('--cancel-path', type=Path, required=True)
    args = parser.parse_args()
    root = tk.Tk()
    root.title('Nachi Native Joint Observer — pendant-controlled pose test')
    root.geometry('1000x625')
    root.minsize(900, 570)
    bg, card_bg, fg, muted = '#111a29', '#1c293d', '#eef4fb', '#a4b5ca'
    root.configure(bg=bg)
    tk.Label(root, text='NACHI  /  NATIVE JOINT OBSERVER', font=('Segoe UI', 19, 'bold'), bg=bg, fg=fg).pack(anchor='w', padx=24, pady=(20, 5))
    tk.Label(root, text='Read-only feedback • You control all movement with the pendant', font=('Segoe UI', 11), bg=bg, fg=muted).pack(anchor='w', padx=24)
    status = tk.Label(root, text='WAITING', font=('Segoe UI', 14, 'bold'), bg=bg, fg='#e7bf6e')
    status.pack(anchor='w', padx=24, pady=(10, 4))
    grid = tk.Frame(root, bg=bg)
    grid.pack(fill='both', expand=True, padx=18, pady=5)
    values, deltas = [], []
    for i in range(6):
        card = tk.Frame(grid, bg=card_bg, padx=16, pady=10)
        card.grid(row=i//3, column=i%3, sticky='nsew', padx=6, pady=6)
        tk.Label(card, text=f'J{i+1}', font=('Segoe UI', 11, 'bold'), bg=card_bg, fg=muted).pack(anchor='w')
        value = tk.Label(card, text='—', font=('Consolas', 27, 'bold'), bg=card_bg, fg=fg)
        value.pack(anchor='w', pady=5)
        delta = tk.Label(card, text='Change from first: —', font=('Segoe UI', 10), bg=card_bg, fg=muted)
        delta.pack(anchor='w')
        values.append(value); deltas.append(delta)
    for i in range(3): grid.columnconfigure(i, weight=1)
    for i in range(2): grid.rowconfigure(i, weight=1)
    summary = tk.Label(root, text='Waiting for receiver', font=('Segoe UI', 11), bg=bg, fg=muted)
    summary.pack(anchor='w', padx=24, pady=8)
    buttons = tk.Frame(root, bg=bg)
    buttons.pack(fill='x', padx=24, pady=5)
    last = {}
    mark_status = tk.Label(root, text='', font=('Segoe UI', 10), bg=bg, fg=muted)

    def mark(name):
        try:
            save_mark(args.data.parent / f'pose-{name.lower()}.json', name, last, time.perf_counter_ns())
            mark_status.configure(text=f'Pose {name} saved locally')
        except (OSError, ValueError) as exc:
            mark_status.configure(text=str(exc))

    def stop():
        try:
            args.cancel_path.write_text('User stopped local observation\n', encoding='utf-8')
            mark_status.configure(text='Stop requested • This stops laptop reads, not the robot')
        except OSError as exc:
            mark_status.configure(text=f'Could not save the Stop request: {exc}')

    tk.Button(buttons, text='Mark pose A', command=lambda: mark('A'), font=('Segoe UI', 11)).pack(side='left', padx=(0, 10))
    tk.Button(buttons, text='Mark pose B', command=lambda: mark('B'), font=('Segoe UI', 11)).pack(side='left')
    tk.Button(buttons, text='Stop observation', command=stop, font=('Segoe UI', 11, 'bold')).pack(side='right')
    mark_status.pack(anchor='w', padx=24, pady=3)
    tk.Label(root, text='Native angle scale • Host receipt age only; controller sample age is unknown\nClosing this display stops laptop reads. It does not stop the robot.',
             font=('Segoe UI', 10), bg=bg, fg=muted, justify='left').pack(anchor='w', padx=24, pady=(4, 15))

    def close():
        try: stop()
        finally: root.destroy()

    def refresh():
        nonlocal last
        try:
            last = json.loads(args.data.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            pass
        badge, recent, age = presentation(last, time.perf_counter_ns())
        status.configure(text=badge, fg='#77d5bd' if recent else '#e7bf6e' if badge in ('WAITING', 'SAVED FINAL') else '#ffac91')
        display_values = last.get('values') if recent or badge == 'SAVED FINAL' else None
        first = last.get('first_values')
        for i in range(6):
            values[i].configure(text=f'{display_values[i]:+.3f}' if display_values and len(display_values)==6 else '—')
            deltas[i].configure(text=f'Change from first: {display_values[i]-first[i]:+.3f}' if display_values and first else 'Change from first: —')
        rate = last.get('receipt_rate_hz')
        age_text = f'{age*1000:.0f} ms' if age is not None and age >= 0 else '—'
        rate_text = f'{rate:.1f}/s' if rate is not None else '—'
        initial = 'Initial 10 samples received' if last.get('initial_samples_received') else 'Keep stationary for initial check'
        summary.configure(text=f'Samples {last.get("samples",0)} • Received {rate_text} • Receipt age {age_text} • Remaining {last.get("remaining_seconds",0):.0f}s\n{initial}')
        if last.get('error'): mark_status.configure(text=last['error'])
        root.after(50, refresh)

    root.protocol('WM_DELETE_WINDOW', close)
    root.lift(); root.attributes('-topmost', True)
    root.after(1500, lambda: root.attributes('-topmost', False))
    refresh()
    root.mainloop()


if __name__ == '__main__':
    main()
