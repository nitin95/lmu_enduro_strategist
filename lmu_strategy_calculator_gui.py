import math
import random
import threading
import tkinter as tk
from tkinter import ttk
from tkinter import messagebox

try:
    import matplotlib
    matplotlib.use('TkAgg')
    import matplotlib.pyplot as plt
    import matplotlib.patches as mpatches
    from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
    _MPL_AVAILABLE = True
except ImportError:
    _MPL_AVAILABLE = False


class LMUStrategyCalculator(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("LMU Race Strategy Calculator")
        self.geometry("1080x720")
        self.resizable(True, True)

        self.defaults = {
            'race_hours': 6,
            'lap_time_s': 105,
            've_full_push': 0.039,
            'N_tires': 100,
            'MAX_STINTS_PER_SET': 2,
            'DT_TIME': 32,
            'chaos_factor': 0.01,
            'WET_RACE': False,
            'wet_ve': 0.043,
            'fuel_to_ve': 1 / 0.8,
            'n_simulations': 1000000,
            'random_seed': 42,
        }

        self.inputs = {}
        self.plan_a = None
        self.plan_b = None
        self.plan_c = None
        self._build_layout()
        self.calculate()

    def _build_layout(self):
        main_frame = ttk.Frame(self, padding=12)
        main_frame.pack(fill='both', expand=True)

        top_frame = ttk.Frame(main_frame)
        top_frame.pack(fill='x', pady=(0, 8))

        self._build_inputs(top_frame)
        self._build_actions(top_frame)

        bottom_frame = ttk.Frame(main_frame)
        bottom_frame.pack(fill='both', expand=True)

        self.tab_control = ttk.Notebook(bottom_frame)
        self.tab_control.pack(fill='both', expand=True)

        self.summary_tab = ttk.Frame(self.tab_control)
        self.ve_tab = ttk.Frame(self.tab_control)
        self.grid_tab = ttk.Frame(self.tab_control)
        self.solver_tab = ttk.Frame(self.tab_control)
        self.comparison_tab = ttk.Frame(self.tab_control)

        self.tab_control.add(self.summary_tab, text='Summary')
        self.tab_control.add(self.ve_tab, text='VE & Fuel')
        self.tab_control.add(self.grid_tab, text='Stint Grid')
        self.tab_control.add(self.solver_tab, text='Monte Carlo Solver')
        self.tab_control.add(self.comparison_tab, text='Strategy Comparison')

        self._build_summary_tab()
        self._build_ve_tab()
        self._build_grid_tab()
        self._build_solver_tab()
        self._build_comparison_tab()

    def _build_inputs(self, parent):
        input_frame = ttk.Labelframe(parent, text='Race Parameters', padding=12)
        input_frame.pack(side='left', fill='x', expand=True)

        rows = [
            ('Race duration (h)', 'race_hours'),
            ('Lap time (s)', 'lap_time_s'),
            ('Full-push VE/lap', 've_full_push'),
            ('Tyre sets available', 'N_tires'),
            ('Max stints per tyre set', 'MAX_STINTS_PER_SET'),
            ('Drive-through penalty (s)', 'DT_TIME'),
            ('Chaos factor', 'chaos_factor'),
            ('Wet race', 'WET_RACE'),
            ('Wet VE/lap', 'wet_ve'),
            ('Fuel → VE conversion', 'fuel_to_ve'),
            ('GA evaluation budget', 'n_simulations'),
            ('Random seed', 'random_seed'),
        ]

        for row, (label, key) in enumerate(rows):
            ttk.Label(input_frame, text=label).grid(row=row, column=0, sticky='w', pady=2)
            if key == 'WET_RACE':
                var = tk.BooleanVar(value=self.defaults[key])
                entry = ttk.Checkbutton(input_frame, variable=var)
                entry.var = var
            else:
                entry = ttk.Entry(input_frame, width=12)
                entry.insert(0, str(self.defaults[key]))
            entry.grid(row=row, column=1, sticky='e', pady=2, padx=(8, 0))
            self.inputs[key] = entry

    def _build_actions(self, parent):
        action_frame = ttk.Frame(parent, padding=12)
        action_frame.pack(side='right', fill='y')

        ttk.Button(action_frame, text='Calculate', command=self.calculate).pack(fill='x', pady=4)
        ttk.Button(action_frame, text='Run Monte Carlo', command=self.start_solver).pack(fill='x', pady=4)
        ttk.Button(action_frame, text='Reset defaults', command=self.reset_defaults).pack(fill='x', pady=4)
        ttk.Button(action_frame, text='Quit', command=self.destroy).pack(fill='x', pady=4)

    def _build_summary_tab(self):
        self.summary_text = tk.Text(self.summary_tab, wrap='word', state='disabled', height=20)
        self.summary_text.pack(fill='both', expand=True, padx=8, pady=8)

    def _build_ve_tab(self):
        self.ve_tree = ttk.Treeview(self.ve_tab, columns=('VE', 'Laps', 'Lap time', 'Fuel'), show='headings', height=8)
        for heading in ('VE', 'Laps', 'Lap time', 'Fuel'):
            self.ve_tree.heading(heading, text=heading)
            self.ve_tree.column(heading, width=120, anchor='center')
        self.ve_tree.pack(fill='both', expand=True, padx=8, pady=8)

    def _build_grid_tab(self):
        self.grid_tree = ttk.Treeview(self.grid_tab,
                                      columns=('Laps', 'FP', 'FP+1', 'FP+2', 'FP+3', 'FP+4'),
                                      show='headings', height=8)
        headers = ['Laps', 'FP', 'FP+1', 'FP+2', 'FP+3', 'FP+4']
        for heading in headers:
            self.grid_tree.heading(heading, text=heading)
            self.grid_tree.column(heading, width=110, anchor='center')
        self.grid_tree.pack(fill='both', expand=True, padx=8, pady=8)

    def _build_solver_tab(self):
        solver_frame = ttk.Frame(self.solver_tab, padding=8)
        solver_frame.pack(fill='both', expand=True)

        self.solver_log = tk.Text(solver_frame, wrap='word', state='disabled', height=12)
        self.solver_log.pack(fill='both', expand=True, pady=(0, 8))

        self.solver_result = ttk.Treeview(solver_frame,
                                          columns=('Stops', 'Laps', 'Pit loss', 'Final VE', 'Info'),
                                          show='tree headings', height=12)
        self.solver_result.column('#0', width=0, stretch=tk.NO)
        for heading, width in [('Stops', 60), ('Laps', 80), ('Pit loss', 80), ('Final VE', 80), ('Info', 200)]:
            self.solver_result.heading(heading, text=heading)
            self.solver_result.column(heading, width=width, anchor='w')
        self.solver_result.pack(fill='both', expand=True)

    def _build_comparison_tab(self):
        outer = ttk.Frame(self.comparison_tab, padding=8)
        outer.pack(fill='both', expand=True)

        # Summary table
        table_frame = ttk.Labelframe(outer, text='Strategy Summary', padding=6)
        table_frame.pack(fill='x', pady=(0, 8))

        cols = ('Metric', 'Plan A', 'Plan B', 'Plan C')
        self.comparison_tree = ttk.Treeview(table_frame, columns=cols, show='headings', height=5)
        self.comparison_tree.heading('Metric', text='Metric')
        self.comparison_tree.column('Metric', width=160, anchor='w')
        for col in ('Plan A', 'Plan B', 'Plan C'):
            self.comparison_tree.heading(col, text=col)
            self.comparison_tree.column(col, width=120, anchor='center')
        self.comparison_tree.pack(fill='x')

        # Chart area
        chart_frame = ttk.Labelframe(outer, text='Stint Bar Chart (race timeline)', padding=6)
        chart_frame.pack(fill='both', expand=True)

        if _MPL_AVAILABLE:
            self.comparison_figure, self.comparison_ax = plt.subplots(figsize=(10, 3))
            self.comparison_figure.patch.set_facecolor('#f0f0f0')
            self.comparison_canvas = FigureCanvasTkAgg(self.comparison_figure, master=chart_frame)
            self.comparison_canvas.get_tk_widget().pack(fill='both', expand=True)
        else:
            self.comparison_canvas = None
            ttk.Label(chart_frame,
                      text='Install matplotlib (pip install matplotlib) to view strategy bar charts.',
                      foreground='grey').pack(expand=True)

        self._update_comparison_tab()

    def reset_defaults(self):
        for key, entry in self.inputs.items():
            if key == 'WET_RACE':
                entry.var.set(self.defaults[key])
            else:
                entry.delete(0, 'end')
                entry.insert(0, str(self.defaults[key]))
        self.calculate()

    def _get_value(self, key, cast):
        entry = self.inputs[key]
        try:
            if key == 'WET_RACE':
                return entry.var.get()
            value = entry.get().strip()
            return cast(value)
        except Exception:
            messagebox.showerror('Input error', f'Invalid value for {key}')
            raise

    def get_inputs(self):
        values = {
            'race_hours': self._get_value('race_hours', float),
            'lap_time_s': self._get_value('lap_time_s', float),
            've_full_push': self._get_value('ve_full_push', float),
            'N_tires': self._get_value('N_tires', float),
            'MAX_STINTS_PER_SET': self._get_value('MAX_STINTS_PER_SET', float),
            'DT_TIME': self._get_value('DT_TIME', float),
            'chaos_factor': self._get_value('chaos_factor', float),
            'WET_RACE': self._get_value('WET_RACE', bool),
            'wet_ve': self._get_value('wet_ve', float),
            'fuel_to_ve': self._get_value('fuel_to_ve', float),
            'n_simulations': int(self._get_value('n_simulations', float)),
            'random_seed': int(self._get_value('random_seed', float)),
        }
        values['race_time_s'] = values['race_hours'] * 3600
        values['laps_approx'] = values['race_time_s'] / values['lap_time_s']
        return values

    def calculate(self):
        data = self.get_inputs()
        self.data = data
        self._calculate_ve_table()
        self._calculate_stint_grid()
        self._update_summary()
        self._clear_solver()

    def _calculate_ve_table(self):
        d = self.data
        laps_fp = math.floor(1 / d['ve_full_push'])
        laps_fp1 = laps_fp + 1
        laps_fp2 = laps_fp1 + 1
        laps_fp3 = laps_fp2 + 1
        laps_fp4 = laps_fp3 + 1
        laps_wet = math.floor(1 / d['wet_ve']) if d['WET_RACE'] else laps_fp1

        d['laps_fp'] = laps_fp
        d['laps_fp1'] = laps_fp1
        d['laps_fp2'] = laps_fp2
        d['laps_fp3'] = laps_fp3
        d['laps_fp4'] = laps_fp4
        d['laps_wet'] = laps_wet

        d['ve_fp1'] = 1 / laps_fp1
        d['ve_fp2'] = 1 / laps_fp2
        d['ve_fp3'] = 1 / laps_fp3
        d['ve_fp4'] = 1 / laps_fp4

        d['fuel_fp'] = d['ve_full_push'] / d['fuel_to_ve'] * 100
        d['fuel_fp1'] = d['ve_fp1'] / d['fuel_to_ve'] * 100
        d['fuel_fp2'] = d['ve_fp2'] / d['fuel_to_ve'] * 100
        d['fuel_fp3'] = d['ve_fp3'] / d['fuel_to_ve'] * 100
        d['fuel_fp4'] = d['ve_fp4'] / d['fuel_to_ve'] * 100

        for row in self.ve_tree.get_children():
            self.ve_tree.delete(row)

        rows = [
            ('Full push', d['ve_full_push'] * 100, laps_fp, d['lap_time_s'], d['fuel_fp']),
            ('+1 lap save', d['ve_fp1'] * 100, laps_fp1, d['lap_time_s'] * 1.01, d['fuel_fp1']),
            ('+2 laps save', d['ve_fp2'] * 100, laps_fp2, d['lap_time_s'] * 1.02, d['fuel_fp2']),
            ('+3 laps save', d['ve_fp3'] * 100, laps_fp3, d['lap_time_s'] * 1.03, d['fuel_fp3']),
            ('+4 laps save', d['ve_fp4'] * 100, laps_fp4, d['lap_time_s'] * 1.04, d['fuel_fp4']),
            ('Wet', d['wet_ve'] * 100, laps_wet, d['lap_time_s'] * 1.2, None),
        ]

        for label, ve, laps, lt, fuel in rows:
            self.ve_tree.insert('', 'end', values=(f'{ve:.2f}%', f'{laps}', f'{lt:.2f}s', f'{fuel:.2f}' if fuel is not None else '—'))

    def _calculate_stint_grid(self):
        d = self.data
        laps_on_plan = math.ceil(d['laps_approx'])
        d['laps_on_plan'] = laps_on_plan
        scenarios = {
            'Negative 2': laps_on_plan - 2,
            'Negative 1': laps_on_plan - 1,
            'On Plan': laps_on_plan,
            'Positive 1': laps_on_plan + 1,
            'Positive 2': laps_on_plan + 2,
        }

        for row in self.grid_tree.get_children():
            self.grid_tree.delete(row)

        for name, laps in scenarios.items():
            self.grid_tree.insert('', 'end', values=(name,
                                                    f'{laps}',
                                                    f'{laps / d["laps_fp1"]:.3f}',
                                                    f'{laps / d["laps_fp2"]:.3f}',
                                                    f'{laps / d["laps_fp3"]:.3f}',
                                                    f'{laps / d["laps_fp4"]:.3f}'))

    def _update_summary(self):
        d = self.data
        laps_on_plan = d['laps_on_plan']
        text = []
        text.append(f"Race duration : {d['race_time_s']:.0f} sec ({d['race_hours']:.1f} h)")
        text.append(f"Lap time      : {d['lap_time_s']:.1f} sec")
        text.append(f"Approx laps   : {d['laps_approx']:.1f}")
        text.append('')
        text.append('VE / Fuel Summary:')
        text.append(f"Full Push VE/lap : {d['ve_full_push']:.4f}")
        text.append(f"VE +1 lap        : {d['ve_fp1']:.4f}")
        text.append(f"VE +2 laps       : {d['ve_fp2']:.4f}")
        text.append(f"VE +3 laps       : {d['ve_fp3']:.4f}")
        text.append(f"VE +4 laps       : {d['ve_fp4']:.4f}")
        text.append('')
        text.append('Strategy Plans:')
        text.append('Plan A: Hard-coded benchmark — full-push stints of laps_fp each, repeated until race ends.')
        text.append('Plan B: Best Genetic Algorithm result \u2014 evolved across all stop counts.')
        text.append('')
        text.append('Genetic Algorithm Solver:')
        text.append('Plan A is computed first as a benchmark. Plan B is the GA result with the most total laps.')
        text.append('GA evaluation budget = pop_size (100) \u00d7 generations derived.')

        self.summary_text.configure(state='normal')
        self.summary_text.delete('1.0', 'end')
        self.summary_text.insert('1.0', '\n'.join(text))
        self.summary_text.configure(state='disabled')

    def _clear_solver(self):
        for row in self.solver_result.get_children():
            self.solver_result.delete(row)

    # ------------------------------------------------------------------
    # Strategy Comparison helpers
    # ------------------------------------------------------------------

    def _compute_stint_segments(self, result):
        """Return a list of segment dicts with timing info for bar chart drawing.

        Each dict has keys: type ('stint' or 'pit'), start_s, end_s, ve_label, stint_num.
        Times are wall-clock seconds from race start (drive time + accumulated pit time).
        """
        d = self.data
        chaos = d['chaos_factor']
        segments = []
        clock = 0.0
        prev = 0
        n_tire_stints = 0

        for i, stop_lap in enumerate(result['stop_laps']):
            stint_laps = stop_lap - prev
            n_tire_stints += 1
            is_tyre_change = n_tire_stints > d['MAX_STINTS_PER_SET']
            label, ve, lt, _ = self.valid_scenario_for(stint_laps)
            if ve is None:
                break
            drive_s = stint_laps * lt * (1 + chaos)
            fuel_l = stint_laps * ve * 100
            pit_s = self.refuel_time(fuel_l, is_tyre_change)

            segments.append({
                'type': 'stint',
                'start_s': clock,
                'end_s': clock + drive_s,
                've_label': label,
                'stint_num': i + 1,
            })
            clock += drive_s
            segments.append({
                'type': 'pit',
                'start_s': clock,
                'end_s': clock + pit_s,
                've_label': None,
                'stint_num': i + 1,
            })
            clock += pit_s
            prev = stop_lap

        # Final stint
        final_laps = result['final_laps']
        label, ve, lt, _ = self.valid_scenario_for(final_laps)
        if ve is not None:
            drive_s = final_laps * lt * (1 + chaos)
            segments.append({
                'type': 'stint',
                'start_s': clock,
                'end_s': clock + drive_s,
                've_label': label,
                'stint_num': len(result['stop_laps']) + 1,
            })

        return segments

    def _update_comparison_tab(self):
        """Refresh the summary table and bar chart on the comparison tab."""
        if not hasattr(self, 'data'):
            return

        # --- Summary table ---
        for row in self.comparison_tree.get_children():
            self.comparison_tree.delete(row)

        plans = [('Plan A', self.plan_a), ('Plan B', self.plan_b), ('Plan C', self.plan_c)]

        def _fmt(result, key, fmt):
            if result is None:
                return 'N/A'
            return fmt.format(result[key])

        metrics = [
            ('Stops',             lambda r: 'N/A' if r is None else str(r['n_stops'])),
            ('Total Laps',        lambda r: 'N/A' if r is None else f'{r["total_laps"]:.2f}'),
            ('Total Pit Time (s)',lambda r: 'N/A' if r is None else f'{r["total_pit_time"]:.0f}'),
            ('Final Stint Fuel (%)', lambda r: 'N/A' if r is None else str(r['final_fuel_l'])),
        ]

        for metric_label, fn in metrics:
            row_vals = (metric_label,) + tuple(fn(r) for _, r in plans)
            self.comparison_tree.insert('', 'end', values=row_vals)

        # --- Bar chart ---
        if not _MPL_AVAILABLE or self.comparison_canvas is None:
            return

        ax = self.comparison_ax
        ax.clear()
        self._draw_strategy_bars(ax, plans)
        self.comparison_figure.tight_layout()
        self.comparison_canvas.draw()

    def _draw_strategy_bars(self, ax, plans):
        """Draw a horizontal Gantt-style bar chart for each strategy plan."""
        d = self.data
        race_s = d['race_time_s']

        VE_COLORS = {
            'Full Push':   '#4c72b0',
            '+1 lap save': '#55a868',
            '+2 laps save':'#c4b526',
            '+3 laps save':'#dd8452',
            '+4 laps save':'#c44e52',
        }
        PIT_COLOR = '#333333'
        NA_COLOR  = '#cccccc'
        STINT_H   = 0.5
        PIT_H     = 0.16

        y_labels = []
        y_ticks  = []

        for i, (label, result) in enumerate(plans):
            y = i
            y_labels.append(label)
            y_ticks.append(y)

            if result is None:
                # Grey "N/A" bar spanning full race width
                ax.barh(y, race_s / 60, left=0, height=STINT_H,
                        color=NA_COLOR, edgecolor='white', linewidth=0.5)
                ax.text(race_s / 60 / 2, y, 'N/A',
                        ha='center', va='center', fontsize=9, color='#555555')
                continue

            segments = self._compute_stint_segments(result)
            for seg in segments:
                start_min = seg['start_s'] / 60
                width_min = (seg['end_s'] - seg['start_s']) / 60

                if seg['type'] == 'pit':
                    ax.barh(y, width_min, left=start_min,
                            height=PIT_H, color=PIT_COLOR,
                            edgecolor=PIT_COLOR, linewidth=0)
                else:
                    color = VE_COLORS.get(seg['ve_label'], NA_COLOR)
                    ax.barh(y, width_min, left=start_min,
                            height=STINT_H, color=color,
                            edgecolor='white', linewidth=0.5)
                    # Annotate stint number if segment is wide enough
                    if width_min / (race_s / 60) > 0.03:
                        ax.text(start_min + width_min / 2, y,
                                str(seg['stint_num']),
                                ha='center', va='center',
                                fontsize=8, color='white', fontweight='bold')

        ax.set_yticks(y_ticks)
        ax.set_yticklabels(y_labels, fontsize=9)
        ax.set_xlabel('Race time (min)', fontsize=9)
        ax.set_xlim(0, race_s / 60)
        ax.xaxis.grid(True, linestyle='--', alpha=0.5)
        ax.set_axisbelow(True)
        ax.set_facecolor('#f8f8f8')

        # Legend
        legend_handles = [mpatches.Patch(color=c, label=lbl)
                          for lbl, c in VE_COLORS.items()]
        legend_handles.append(mpatches.Patch(color=PIT_COLOR, label='Pit stop'))
        ax.legend(handles=legend_handles, loc='lower right',
                  fontsize=7, ncol=3, framealpha=0.8)
        self._append_solver_log('Press Run Monte Carlo to search for optimal stop counts.')

    def _append_solver_log(self, message):
        self.solver_log.configure(state='normal')
        self.solver_log.insert('end', message + '\n')
        self.solver_log.see('end')
        self.solver_log.configure(state='disabled')

    def _format_stint_details(self, result, prev_lap=0):
        """Format stint details for display in the tree view."""
        details = []
        d = self.data
        
        for i, stop_lap in enumerate(result['stop_laps']):
            stint_laps = stop_lap - prev_lap
            label, ve, lt, _ = self.valid_scenario_for(stint_laps)
            fuel_l = stint_laps * ve * 100
            details.append(f"Stint {i+1}: Laps {prev_lap}–{stop_lap} ({stint_laps} laps) | {label} | VE={ve:.4f} | Fuel={fuel_l:.1f}L")
            prev_lap = stop_lap
        
        # Final stint
        final_laps = result['final_laps']
        label, ve, lt, _ = self.valid_scenario_for(final_laps)
        fuel_l = final_laps * ve * 100
        details.append(f"Stint {len(result['stop_laps'])+1}: Laps {prev_lap}–end (~{final_laps:.1f} laps) | {label} | VE={ve:.4f} | Fuel={fuel_l:.1f}L")
        
        return details

    def valid_scenario_for(self, stint_laps):
        d = self.data
        max_fp = d['laps_fp']
        if stint_laps <= max_fp:
            return 'Full Push', d['ve_full_push'], d['lap_time_s'], max_fp
        for label, ve, lt, laps in [
            ('+1 lap save', d['ve_fp1'], d['lap_time_s'] * 1.01, d['laps_fp1']),
            ('+2 laps save', d['ve_fp2'], d['lap_time_s'] * 1.02, d['laps_fp2']),
            ('+3 laps save', d['ve_fp3'], d['lap_time_s'] * 1.03, d['laps_fp3']),
            ('+4 laps save', d['ve_fp4'], d['lap_time_s'] * 1.04, d['laps_fp4']),
        ]:
            if stint_laps <= laps:
                return label, ve, lt, laps
        return None, None, None, None

    def evaluate_strategy(self, stop_laps):
        d = self.data
        total_pit = 0.0
        elapsed_drive = 0.0
        prev = 0
        n_tire_stints = 0

        for stop in stop_laps:
            stint_laps = stop - prev
            n_tire_stints += 1
            is_tyre_change = n_tire_stints > d['MAX_STINTS_PER_SET']
            label, ve, lt, max_laps = self.valid_scenario_for(stint_laps)
            if ve is None:
                return None
            if stint_laps < (1 / d['ve_full_push']) * 0.7 or stint_laps * ve > 1.02:
                return None
            fuel_l = stint_laps * ve * 100
            total_pit += self.refuel_time(fuel_l, is_tyre_change)
            elapsed_drive += stint_laps * lt * (1 + d['chaos_factor'])
            prev = stop

        remaining = d['race_time_s'] - elapsed_drive - total_pit
        if remaining <= 0:
            return None
        final_laps = remaining / (d['lap_time_s'] * (1 + d['chaos_factor']))
        if final_laps < (1 / d['ve_full_push']) * 0.7 or final_laps * d['ve_full_push'] > 1.02:
            return None

        total_laps = stop_laps[-1] + final_laps
        final_fuel_l = math.ceil(math.ceil(final_laps) * d['ve_full_push'] * 100)
        return {
            'stop_laps': stop_laps,
            'n_stops': len(stop_laps),
            'total_pit_time': total_pit,
            'final_laps': final_laps,
            'total_laps': total_laps,
            'final_fuel_l': final_fuel_l,
        }

    def refuel_time(self, ve_refill, is_tyre_change):
        if is_tyre_change:
            return ve_refill * 0.4 + 22.0 + self.data['DT_TIME']
        return ve_refill * 0.4 + self.data['DT_TIME']

    def compute_plan_a(self):
        """Hard-coded benchmark: spam full-push stints of laps_fp each until the race ends."""
        d = self.data
        laps_fp = d['laps_fp']
        lt = d['lap_time_s']
        ve = d['ve_full_push']
        chaos = d['chaos_factor']
        race_time = d['race_time_s']
        fuel_per_stint = laps_fp * ve * 100

        stop_laps = []
        total_drive = 0.0
        total_pit = 0.0
        current_lap = 0
        n_tire_stints = 0

        while True:
            n_tire_stints += 1
            is_tyre_change = n_tire_stints > d['MAX_STINTS_PER_SET']
            stint_drive = laps_fp * lt * (1 + chaos)
            pit = self.refuel_time(fuel_per_stint, is_tyre_change)
            if total_drive + stint_drive + total_pit + pit >= race_time:
                break
            total_drive += stint_drive
            total_pit += pit
            current_lap += laps_fp
            stop_laps.append(current_lap)

        remaining = race_time - total_drive - total_pit
        if remaining <= 0:
            return None
        final_laps = remaining / (lt * (1 + chaos))
        total_laps = current_lap + final_laps
        final_fuel_l = math.ceil(math.ceil(final_laps) * ve * 100)
        return {
            'stop_laps': stop_laps,
            'n_stops': len(stop_laps),
            'total_pit_time': total_pit,
            'final_laps': final_laps,
            'total_laps': total_laps,
            'final_fuel_l': final_fuel_l,
        }

    def sample_stop_laps(self, rng, n_stops, lo, hi, gap):
        n_stops = int(n_stops)
        if n_stops == 0:
            return []
        available = int(hi - lo - (n_stops - 1) * gap)
        if available <= 0:
            return None
        raw = sorted(rng.randint(0, available) for _ in range(n_stops))
        return [lo + raw[i] + i * gap for i in range(n_stops)]

    def random_strategy(self, rng, n_stops, hard_ceil, min_stint):
        stop_laps = self.sample_stop_laps(rng, n_stops, lo=min_stint, hi=hard_ceil - min_stint, gap=min_stint)
        if stop_laps is None:
            return None
        result = self.evaluate_strategy(stop_laps)
        return result

    def start_solver(self):
        try:
            d = self.get_inputs()
        except Exception:
            return
        self.calculate()
        self.solver_result.delete(*self.solver_result.get_children())
        self.solver_log.configure(state='normal')
        self.solver_log.delete('1.0', 'end')
        self.solver_log.configure(state='disabled')
        thread = threading.Thread(target=self._run_solver, daemon=True)
        thread.start()

    def _display_plan(self, result, label):
        parent = self.solver_result.insert('', 'end',
                                           values=(result['n_stops'],
                                                   f'{result["total_laps"]:.2f}',
                                                   f'{result["total_pit_time"]:.0f}s',
                                                   f'{result["final_fuel_l"]}%',
                                                   label),
                                           open=True)
        stint_details = self._format_stint_details(result)
        for detail in stint_details:
            self.solver_result.insert(parent, 'end', values=('', '', '', '', detail))

    def _run_solver(self):
        d = self.data
        POP_SIZE = 100
        N_GEN = max(20, d['n_simulations'] // POP_SIZE)
        ELITE_N = max(2, POP_SIZE // 10)
        TOURNAMENT_K = 5
        CROSSOVER_RATE = 0.7
        MUTATION_RATE = 0.4

        rng = random.Random(d['random_seed'])
        min_stint = int(math.floor((1 / d['ve_full_push']) * 0.8))
        hard_ceil = int(d['race_time_s'] / d['lap_time_s'])
        

        plan_a = self.compute_plan_a()
        if plan_a is None:
            self._append_solver_log('Could not compute Plan A. Check parameters.')
            return

        max_stops = plan_a['n_stops']

        self._append_solver_log(
            f'Plan A benchmark: {plan_a["n_stops"]} stops \u2192 {plan_a["total_laps"]:.2f} laps')
        self._append_solver_log(
            f'Starting GA (Plan B): pop={POP_SIZE}, generations={N_GEN}...')

        def make_individual():
            n = rng.randint(1, max_stops)
            return self.sample_stop_laps(rng, n, min_stint, hard_ceil - min_stint, min_stint)

        def evaluate(ind):
            if not ind:
                return None
            return self.evaluate_strategy(ind)

        def tournament(pop_fit):
            pool = [pop_fit[rng.randrange(len(pop_fit))] for _ in range(TOURNAMENT_K)]
            valid_pool = [(ind, res) for ind, res in pool if res is not None]
            if valid_pool:
                return max(valid_pool, key=lambda x: x[1]['total_laps'])[0]
            return pool[0][0]

        def crossover(p1, p2):
            combined = sorted(set(p1 + p2))
            if not combined:
                return p1[:]
            size = rng.randint(min(len(p1), len(p2)), max(len(p1), len(p2)))
            size = max(1, min(size, len(combined), max_stops))
            return sorted(rng.sample(combined, size))

        def mutate(ind):
            ind = ind[:]
            op = rng.random()
            if op < 0.33 and len(ind) > 1:
                ind.pop(rng.randrange(len(ind)))
            elif op < 0.66 and len(ind) < max_stops:
                new_stop = rng.randint(min_stint, max(min_stint, hard_ceil - min_stint))
                ind = sorted(set(ind + [new_stop]))
            else:
                idx = rng.randrange(len(ind))
                delta = rng.randint(-min_stint, min_stint)
                shifted = max(min_stint, min(hard_ceil - min_stint, ind[idx] + delta))
                ind[idx] = shifted
                ind = sorted(set(ind))
            return ind or [rng.randint(min_stint, max(min_stint, hard_ceil - min_stint))]

        # Seed initial population
        population = []
        while len(population) < POP_SIZE:
            ind = make_individual()
            if ind:
                population.append(ind)

        best_result = None

        for gen in range(N_GEN):
            pop_fit = [(ind, evaluate(ind)) for ind in population]
            valid = [(ind, res) for ind, res in pop_fit if res is not None]

            if valid:
                gen_best = max(valid, key=lambda x: x[1]['total_laps'])[1]
                if best_result is None or gen_best['total_laps'] > best_result['total_laps']:
                    best_result = gen_best

            if gen % max(1, N_GEN // 10) == 0:
                b = f'{best_result["total_laps"]:.2f}' if best_result else '\u2014'
                self._append_solver_log(
                    f'[Plan B] Gen {gen + 1}/{N_GEN} | valid={len(valid)} | best={b} laps')

            # Build next generation
            new_pop = []

            # Elitism: carry over top individuals unchanged
            if valid:
                for ind, _ in sorted(valid, key=lambda x: x[1]['total_laps'], reverse=True)[:ELITE_N]:
                    new_pop.append(ind[:])

            while len(new_pop) < POP_SIZE:
                p1 = tournament(pop_fit)
                if rng.random() < CROSSOVER_RATE:
                    p2 = tournament(pop_fit)
                    child = crossover(p1, p2)
                else:
                    child = p1[:]
                if rng.random() < MUTATION_RATE:
                    child = mutate(child)
                new_pop.append(child)

            population = new_pop

        self._append_solver_log('Plan B GA complete.')
        self._display_plan(plan_a, 'Plan A \u2014 Full Push Benchmark')

        plan_b = best_result
        if plan_b:
            diff = plan_b['total_laps'] - plan_a['total_laps']
            sign = '+' if diff >= 0 else ''
            self._display_plan(
                plan_b, f'Plan B \u2014 Best GA ({sign}{diff:.2f} vs Plan A)')
        else:
            self._append_solver_log('No valid Plan B found.')

        # ------------------------------------------------------------------
        # Plan C: GA constrained to exactly (plan_a stops - 1)
        # ------------------------------------------------------------------
        target_c = plan_a['n_stops'] - 1
        plan_c = None

        if target_c < 1:
            self._append_solver_log(
                'Plan C not applicable \u2014 Plan A already at minimum stops (1).')
        else:
            self._append_solver_log(
                f'Starting GA (Plan C): exactly {target_c} stop(s), '
                f'pop={POP_SIZE}, generations={N_GEN}...')

            def make_individual_c():
                return self.sample_stop_laps(
                    rng, target_c, min_stint, hard_ceil - min_stint, min_stint)

            def crossover_c(p1, p2):
                combined = sorted(set(p1 + p2))
                if len(combined) < target_c:
                    # Pool too small — return a copy of the longer parent
                    return (p1 if len(p1) >= len(p2) else p2)[:]
                return sorted(rng.sample(combined, target_c))

            def mutate_c(ind):
                """Shift-only mutation to keep stop count fixed."""
                ind = ind[:]
                idx = rng.randrange(len(ind))
                delta = rng.randint(-min_stint, min_stint)
                shifted = max(min_stint, min(hard_ceil - min_stint, ind[idx] + delta))
                ind[idx] = shifted
                ind = sorted(set(ind))
                # If a collision removed a stop, add a random replacement
                while len(ind) < target_c:
                    new_stop = rng.randint(min_stint, max(min_stint, hard_ceil - min_stint))
                    ind = sorted(set(ind + [new_stop]))
                return ind

            def tournament_c(pop_fit_c):
                pool = [pop_fit_c[rng.randrange(len(pop_fit_c))]
                        for _ in range(TOURNAMENT_K)]
                valid_pool = [(ind, res) for ind, res in pool if res is not None]
                if valid_pool:
                    return max(valid_pool, key=lambda x: x[1]['total_laps'])[0]
                return pool[0][0]

            population_c = []
            attempts = 0
            while len(population_c) < POP_SIZE and attempts < POP_SIZE * 50:
                ind = make_individual_c()
                if ind and evaluate(ind) is not None:
                    population_c.append(ind)
                attempts += 1

            if not population_c:
                self._append_solver_log(
                    'Plan C not feasible \u2014 could not seed a valid population '
                    f'with {target_c} stop(s).')
            else:
                # Pad population if seeding was slow
                while len(population_c) < POP_SIZE:
                    population_c.append(population_c[rng.randrange(len(population_c))][:])

                best_c = None

                for gen in range(N_GEN):
                    pop_fit_c = [(ind, evaluate(ind)) for ind in population_c]
                    valid_c = [(ind, res) for ind, res in pop_fit_c if res is not None]

                    if valid_c:
                        gen_best_c = max(valid_c, key=lambda x: x[1]['total_laps'])[1]
                        if best_c is None or gen_best_c['total_laps'] > best_c['total_laps']:
                            best_c = gen_best_c

                    if gen % max(1, N_GEN // 10) == 0:
                        b = f'{best_c["total_laps"]:.2f}' if best_c else '\u2014'
                        self._append_solver_log(
                            f'[Plan C] Gen {gen + 1}/{N_GEN} | valid={len(valid_c)} | best={b} laps')

                    new_pop_c = []
                    if valid_c:
                        for ind, _ in sorted(valid_c,
                                             key=lambda x: x[1]['total_laps'],
                                             reverse=True)[:ELITE_N]:
                            new_pop_c.append(ind[:])

                    while len(new_pop_c) < POP_SIZE:
                        p1 = tournament_c(pop_fit_c)
                        if rng.random() < CROSSOVER_RATE:
                            p2 = tournament_c(pop_fit_c)
                            child = crossover_c(p1, p2)
                        else:
                            child = p1[:]
                        if rng.random() < MUTATION_RATE:
                            child = mutate_c(child)
                        new_pop_c.append(child)

                    population_c = new_pop_c

                self._append_solver_log('Plan C GA complete.')
                plan_c = best_c

                if plan_c:
                    diff_c = plan_c['total_laps'] - plan_a['total_laps']
                    sign_c = '+' if diff_c >= 0 else ''
                    self._display_plan(
                        plan_c,
                        f'Plan C \u2014 One Fewer Stop GA ({sign_c}{diff_c:.2f} vs Plan A)')
                else:
                    self._append_solver_log('No valid Plan C found.')

        # Store for comparison tab and refresh it on the main thread
        self.plan_a = plan_a
        self.plan_b = plan_b
        self.plan_c = plan_c
        self.after(0, self._update_comparison_tab)

    def run(self):
        self.mainloop()


if __name__ == '__main__':
    app = LMUStrategyCalculator()
    app.run()
