import math
import random
import threading
import tkinter as tk
from tkinter import ttk
from tkinter import messagebox


class LMUStrategyCalculator(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("LMU Race Strategy Calculator")
        self.geometry("1080x720")
        self.resizable(True, True)

        self.defaults = {
            'race_hours': 24,
            'lap_time_s': 242,
            've_full_push': 0.095,
            'N_tires': 100,
            'MAX_STINTS_PER_SET': 2.5,
            'DT_TIME': 32,
            'chaos_factor': 0.01,
            'WET_RACE': False,
            'wet_ve': 0.043,
            'fuel_to_ve': 1 / 0.8,
            'n_simulations': 10000,
            'random_seed': 42,
        }

        self.inputs = {}
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

        self.tab_control.add(self.summary_tab, text='Summary')
        self.tab_control.add(self.ve_tab, text='VE & Fuel')
        self.tab_control.add(self.grid_tab, text='Stint Grid')
        self.tab_control.add(self.solver_tab, text='Monte Carlo Solver')

        self._build_summary_tab()
        self._build_ve_tab()
        self._build_grid_tab()
        self._build_solver_tab()

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
            ('Monte Carlo simulations', 'n_simulations'),
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
        text.append('Strategy Plan Notes:')
        text.append('Plan A: Full-push pace, N stops')
        text.append('Plan B: Fuel-save pace, same N stops')
        text.append('Plan C: Full-push pace, N - 1 stops')
        text.append('')
        text.append('Monte Carlo Solver:')
        text.append('Use the Run Monte Carlo button for a best-fit stop count search.')

        self.summary_text.configure(state='normal')
        self.summary_text.delete('1.0', 'end')
        self.summary_text.insert('1.0', '\n'.join(text))
        self.summary_text.configure(state='disabled')

    def _clear_solver(self):
        for row in self.solver_result.get_children():
            self.solver_result.delete(row)
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

    def _run_solver(self):
        d = self.data
        rng = random.Random(d['random_seed'])
        min_stint = (1 / d['ve_full_push']) * 0.7
        hard_ceil = int(d['race_time_s'] / d['lap_time_s'])
        max_stops = max(1, int(d['laps_on_plan'] / max(1, min_stint)))
        max_stops = min(max_stops, 10)

        valid_by_stops = {}
        valid_count = 0

        self._append_solver_log(f'Starting Monte Carlo with {d["n_simulations"]:,} simulations...')

        for i in range(d['n_simulations']):
            n_stops = rng.randint(1, max_stops)
            result = self.random_strategy(rng, n_stops, hard_ceil, min_stint)
            if result is None:
                continue
            valid_count += 1
            score = result['total_laps']
            if n_stops not in valid_by_stops or score > valid_by_stops[n_stops]['total_laps']:
                valid_by_stops[n_stops] = result
            if i > 0 and i % max(1, d['n_simulations'] // 10) == 0:
                self._append_solver_log(f'Progress: {i}/{d["n_simulations"]} simulations, valid={valid_count}')

        if not valid_by_stops:
            self._append_solver_log('No valid strategies found. Adjust parameters and try again.')
            return

        best_overall = max(valid_by_stops.values(), key=lambda r: r['total_laps'])
        self._append_solver_log(f'Valid strategies found: {valid_count}')
        self._append_solver_log(f'Best overall: {best_overall["n_stops"]} stops → {best_overall["total_laps"]:.2f} laps')

        for n_stops in sorted(valid_by_stops):
            result = valid_by_stops[n_stops]
            is_best = '🗿 ' if result is best_overall else ''
            parent = self.solver_result.insert('', 'end', 
                                               values=(n_stops,
                                                       f'{result["total_laps"]:.2f}',
                                                       f'{result["total_pit_time"]:.0f}',
                                                       f'{result["final_fuel_l"]}%',
                                                       f'{is_best}Stop laps: {result["stop_laps"]}'),
                                               open=False)
            
            # Insert stint details as child rows
            stint_details = self._format_stint_details(result)
            for detail in stint_details:
                self.solver_result.insert(parent, 'end', values=('', '', '', '', detail))

        self._append_solver_log('Solver complete.')

    def run(self):
        self.mainloop()


if __name__ == '__main__':
    app = LMUStrategyCalculator()
    app.run()
