from matplotlib import pyplot as plt
from matplotlib.collections import LineCollection
import numpy as np

from skyfield.api import Star, wgs84
from skyfield.positionlib import position_of_radec
from skyfield.projections import build_stereographic_projection

from starplot.base import StarPlot
from starplot.data import load, constellations, stars, dsos
from starplot.utils import in_circle


def create_projected_constellation_lines(stardata_projected):
    consdata = constellations.load()
    stars_1 = []
    stars_2 = []
    for _, lines in consdata:
        any_star_in_view = False
        constars_1 = []
        constars_2 = []
        for s1, s2 in lines:
            sx1, sy1 = stardata_projected[["x", "y"]].loc[s1].values
            sx2, sy2 = stardata_projected[["x", "y"]].loc[s2].values
            if in_circle(sx1, sy1, radius=1.1) or in_circle(sx2, sy2, radius=1.1):
                any_star_in_view = True
            constars_1.append(s1)
            constars_2.append(s2)

        if any_star_in_view:
            stars_1.extend(constars_1)
            stars_2.extend(constars_2)

    xy1 = stardata_projected[["x", "y"]].loc[stars_1].values
    xy2 = stardata_projected[["x", "y"]].loc[stars_2].values

    return np.rollaxis(np.array([xy1, xy2]), 1)


class ZenithPlot(StarPlot):
    def __init__(
        self,
        lat: float = None,
        lon: float = None,
        include_info_text: bool = False,
        *args,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        self.lat = lat
        self.lon = lon
        self.include_info_text = include_info_text

        self._calc_position()
        self.project_fn = build_stereographic_projection(self.position)

        self._init_plot()

    def in_bounds(self, ra, dec) -> bool:
        x, y = self._prepare_coords(ra, dec)
        result = in_circle(x, y)
        return result

    def _prepare_coords(self, ra, dec) -> (float, float):
        return self.project_fn(position_of_radec(ra, dec))

    def _calc_position(self):
        loc = wgs84.latlon(self.lat, self.lon).at(self.timescale)
        self.position = loc.from_altaz(alt_degrees=90, az_degrees=0)

    def _plot_constellation_lines(self):
        constellations = LineCollection(
            create_projected_constellation_lines(self._stardata),
            **self.style.constellation.line.matplot_kwargs(
                size_multiplier=self._size_multiplier
            ),
        )
        self._plotted_conlines = self.ax.add_collection(constellations)

    def _plot_constellation_labels(self):
        for con in constellations.iterator():
            fullname, ra, dec = constellations.get(con)
            x, y = self.project_fn(position_of_radec(ra, dec))

            if in_circle(x, y):
                label = self.ax.text(
                    x,
                    y,
                    fullname.upper(),
                    path_effects=[self.text_border],
                    **self.style.constellation.label.matplot_kwargs(
                        size_multiplier=self._size_multiplier
                    ),
                )
                self._maybe_remove_label(label)

    def _plot_stars(self):
        stardata = stars.load(self.limiting_magnitude)
        self._stardata = stardata

        eph = load(self.ephemeris)
        earth = eph["earth"]

        # project stars to stereographic plot
        star_positions = earth.at(self.timescale).observe(Star.from_dataframe(stardata))
        stardata["x"], stardata["y"] = self.project_fn(star_positions)

        # filter stars by limiting magnitude
        bright_stars = stardata.magnitude <= self.limiting_magnitude

        # calculate size of each star based on magnitude
        sizes = []
        for m in stardata["magnitude"][bright_stars]:
            if m < 2:
                sizes.append((8 - m) ** 2.56 * (self._size_multiplier**2))
            else:
                # sizes.append((1 + self.limiting_magnitude - m) ** 2 * self._size_multiplier)
                sizes.append((8 - m) ** 1.36 * (self._size_multiplier**2))

        # Draw stars
        self._plotted_stars = self.ax.scatter(
            stardata["x"][bright_stars],
            stardata["y"][bright_stars],
            sizes,
            color=self.style.star.marker.color.as_hex(),
        )

        starpos_x = []
        starpos_y = []

        # Plot star names
        for i, s in stardata[bright_stars].iterrows():
            if (
                in_circle(s["x"], s["y"])
                and i in stars.hip_names
                and s["magnitude"] < self.limiting_magnitude_labels
            ):
                label = self.ax.text(
                    s["x"] + 0.00984,
                    s["y"] - 0.006,
                    stars.hip_names[i],
                    **self.style.star.label.matplot_kwargs(
                        size_multiplier=self._size_multiplier
                    ),
                    ha="left",
                    va="top",
                    path_effects=[self.text_border],
                )
                label.set_alpha(self.style.star.label.font_alpha)
                label.set_clip_on(True)
                self._maybe_remove_label(label)

                starpos_x.append(s["x"])
                starpos_y.append(s["y"])

    def _plot_dso_base(self):
        for m in dsos.ZENITH_BASE:
            ra, dec = dsos.messier.get(m)
            x, y = self.project_fn(position_of_radec(ra, dec))

            if in_circle(x, y):
                self.ax.plot(
                    x,
                    y,
                    **self.style.dso.marker.matplot_kwargs(
                        size_multiplier=self._size_multiplier
                    ),
                )
                label = self.ax.text(
                    x + self.style.text_offset_x,
                    y + self.style.text_offset_y,
                    m.upper(),
                    ha="right",
                    va="center",
                    **self.style.dso.label.matplot_kwargs(
                        size_multiplier=self._size_multiplier
                    ),
                    path_effects=[self.text_border],
                )
                self._maybe_remove_label(label)

    def _plot_border(self):
        # Plot border text
        border_font_kwargs = dict(
            fontsize=self.style.border_font_size * self._size_multiplier * 2,
            weight=self.style.border_font_weight,
            color=self.style.border_font_color.as_hex(),
        )
        self.ax.text(0, 1.009, "N", **border_font_kwargs)
        self.ax.text(1.003, 0, "W", **border_font_kwargs)
        self.ax.text(-1.042, 0, "E", **border_font_kwargs)
        self.ax.text(0, -1.045, "S", **border_font_kwargs)

        # Background Circle
        background_circle = plt.Circle(
            (0, 0),
            facecolor=self.style.background_color.as_hex(),
            radius=1.0,
            linewidth=0,
            fill=True,
            zorder=-100,
        )
        self.ax.add_patch(background_circle)

        # clip stars outside background circle
        self._plotted_stars.set_clip_path(background_circle)
        self._plotted_conlines.set_clip_path(background_circle)

        # Border Circles
        inner_border = plt.Circle(
            (0, 0),
            radius=1.0,
            linewidth=2 * self._size_multiplier,
            edgecolor=self.style.border_line_color.as_hex(),
            fill=False,
            zorder=100,
        )
        self.ax.add_patch(inner_border)

        # Outer border circle
        outer_border = plt.Circle(
            (0, 0),
            facecolor=self.style.border_bg_color.as_hex(),
            radius=1.06,
            linewidth=4 * self._size_multiplier,
            edgecolor=self.style.border_line_color.as_hex(),
            fill=True,
            zorder=-200,
        )
        self.ax.add_patch(outer_border)

    def _init_plot(self):
        self.fig = plt.figure(figsize=(self.figure_size, self.figure_size))
        self.ax = plt.axes()

        self.ax.set_xlim(-1.1, 1.1)
        self.ax.set_ylim(-1.1, 1.1)
        self.ax.xaxis.set_visible(False)
        self.ax.yaxis.set_visible(False)
        self.ax.set_aspect(1.0)
        self.ax.axis("off")

        self._plot_stars()
        self._plot_constellation_lines()
        self._plot_constellation_labels()
        self._plot_dso_base()
        self._plot_border()

        if self.include_info_text:
            dt_str = self.dt.strftime("%m/%d/%Y @ %H:%M:%S") + " " + self.dt.tzname()
            info = f"{str(self.lat)}, {str(self.lon)}\n{dt_str}"
            self.ax.text(
                -1.03, -1.03, info, fontsize=13, family="monospace", linespacing=2
            )

        if self.adjust_text:
            self.adjust_labels()