/* SPDX-License-Identifier: LGPL-2.1-or-later */

#include <array>
#include <cassert>
#include <cstdint>
#include <limits>
#include <span>
#include <vector>

#include "../files/camera/atomisp-yuv.h"

using latte::YuvPlane;
using latte::YuvStats;
using latte::YuvWindow;
using latte::calculateYuv420Stats;

int main()
{
	std::vector<uint8_t> y(8 * 2, 100);
	std::vector<uint8_t> u{ 128, 128, 0, 128 };
	std::vector<uint8_t> v{ 128, 128, 255, 128 };
	std::array<YuvPlane, 3> planes{ YuvPlane{ y, 8 }, YuvPlane{ u, 4 }, YuvPlane{ v, 4 } };
	YuvStats stats;

	assert(calculateYuv420Stats(planes, 8, 2, { 0, 0, 8, 2 }, stats));
	assert(stats.histogram[25] == 2);
	assert(stats.red > stats.green);
	assert(stats.blue < stats.green);

	std::vector<uint8_t> paddedY(7 * 4 + 3, 0);
	std::vector<uint8_t> paddedU(4 * 2 + 2, 128);
	std::vector<uint8_t> paddedV(4 * 2 + 2, 128);
	paddedY[2 + 7 + 1] = 200;
	planes = { YuvPlane{ std::span(paddedY).subspan(2), 7 },
		   YuvPlane{ std::span(paddedU).subspan(1), 4 },
		   YuvPlane{ std::span(paddedV).subspan(1), 4 } };
	assert(calculateYuv420Stats(planes, 6, 4, { 1, 1, 1, 1 }, stats));
	assert(stats.histogram[50] == 1);
	assert(stats.red == stats.green && stats.green == stats.blue);

	stats.red = 42;
	planes[1].bytes = planes[1].bytes.first(6);
	assert(!calculateYuv420Stats(planes, 6, 4, { 0, 0, 6, 4 }, stats));
	assert(stats.red == 42);
	planes[1].bytes = std::span(paddedU).subspan(1);
	assert(!calculateYuv420Stats(planes, 6, 4, { 5, 0, 2, 1 }, stats));
	assert(!calculateYuv420Stats(planes, 5, 4, { 0, 0, 5, 4 }, stats));
	assert(!calculateYuv420Stats(planes, 6, 4, { 0, 0, 0, 4 }, stats));
	planes[0].stride = std::numeric_limits<size_t>::max();
	assert(!calculateYuv420Stats(planes, 6, 4, { 0, 0, 6, 4 }, stats));

	for (size_t width = 2; width <= 24; width += 2) {
		for (size_t height = 2; height <= 18; height += 2) {
			const size_t yStride = width + 3;
			const size_t uvStride = width / 2 + 2;
			std::vector<uint8_t> yy((height - 1) * yStride + width, 16);
			std::vector<uint8_t> uu((height / 2 - 1) * uvStride + width / 2, 128);
			std::vector<uint8_t> vv(uu.size(), 128);
			planes = { YuvPlane{ yy, yStride }, YuvPlane{ uu, uvStride },
				   YuvPlane{ vv, uvStride } };
			for (size_t x = 0; x < width; ++x) {
				for (size_t row = 0; row < height; ++row) {
					const YuvWindow window{ x, row, width - x, height - row };
					assert(calculateYuv420Stats(planes, width, height, window, stats));
					const size_t samples = ((window.width - 1) / 4 + 1) *
							       ((window.height - 1) / 4 + 1);
					assert(stats.histogram[4] == samples);
					assert(stats.red == 0 && stats.green == 0 && stats.blue == 0);
				}
			}
			planes[2].bytes = planes[2].bytes.first(vv.size() - 1);
			assert(!calculateYuv420Stats(planes, width, height,
						     { 0, 0, width, height }, stats));
		}
	}
}
