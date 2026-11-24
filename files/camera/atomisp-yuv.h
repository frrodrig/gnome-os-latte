/* SPDX-License-Identifier: LGPL-2.1-or-later */

#pragma once

#include <algorithm>
#include <array>
#include <cstddef>
#include <cstdint>
#include <limits>
#include <span>

namespace latte {

struct YuvPlane {
	std::span<const uint8_t> bytes;
	size_t stride;
};

struct YuvWindow {
	size_t x;
	size_t y;
	size_t width;
	size_t height;
};

struct YuvStats {
	std::array<uint32_t, 64> histogram{};
	uint64_t red = 0;
	uint64_t green = 0;
	uint64_t blue = 0;
};

inline bool planeContains(const YuvPlane &plane, size_t width, size_t height)
{
	if (!width || !height || plane.stride < width || plane.bytes.size() < width)
		return false;

	return height - 1 <= (plane.bytes.size() - width) / plane.stride;
}

inline bool calculateYuv420Stats(const std::array<YuvPlane, 3> &planes,
				 size_t width, size_t height,
				 const YuvWindow &window, YuvStats &result)
{
	if (!width || !height || width % 2 || height % 2 ||
	    !window.width || !window.height ||
	    window.x >= width || window.y >= height ||
	    window.width > width - window.x ||
	    window.height > height - window.y ||
	    !planeContains(planes[0], width, height) ||
	    !planeContains(planes[1], width / 2, height / 2) ||
	    !planeContains(planes[2], width / 2, height / 2))
		return false;

	const size_t columns = (window.width - 1) / 4 + 1;
	const size_t rows = (window.height - 1) / 4 + 1;
	if (rows > std::numeric_limits<uint32_t>::max() / columns)
		return false;

	YuvStats stats;
	for (size_t y = 0; y < window.height; y += 4) {
		const size_t row = window.y + y;
		for (size_t x = 0; x < window.width; x += 4) {
			const size_t column = window.x + x;
			const int luma = planes[0].bytes[row * planes[0].stride + column];
			const int u = planes[1].bytes[(row / 2) * planes[1].stride + column / 2] - 128;
			const int v = planes[2].bytes[(row / 2) * planes[2].stride + column / 2] - 128;
			const int scaledY = 298 * (luma - 16);
			stats.histogram[luma / 4]++;
			stats.red += std::clamp((scaledY + 459 * v + 128) / 256, 0, 255);
			stats.green += std::clamp((scaledY - 55 * u - 136 * v + 128) / 256, 0, 255);
			stats.blue += std::clamp((scaledY + 541 * u + 128) / 256, 0, 255);
		}
	}
	result = stats;
	return true;
}

} /* namespace latte */
